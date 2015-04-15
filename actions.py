#!/usr/bin/python

# Copyright (C) 2015  Jaroslav Henner
#
# This file is part of pyvmomi ansible module.
#
# pyvmomi ansible module is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# pyvmomi ansible module is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyvmomi ansible more.  If not, see <http://www.gnu.org/licenses/>.

from abc import abstractmethod
from contextlib import contextmanager
import logging
from time import sleep
import uuid

from pyVim import connect
from pyVmomi import vim
from pyVmomi import vmodl


LOG = logging.getLogger(__name__)


def wait_for_tasks(service_instance, tasks):
    """Given the service instance si and tasks, it returns after all the
   tasks are complete
   """
    property_collector = service_instance.content.propertyCollector
    task_list = [str(task) for task in tasks]
    # Create filter
    obj_specs = [vmodl.query.PropertyCollector.ObjectSpec(obj=task)
                 for task in tasks]
    property_spec = vmodl.query.PropertyCollector.PropertySpec(type=vim.Task,
                                                               pathSet=[],
                                                               all=True)
    filter_spec = vmodl.query.PropertyCollector.FilterSpec()
    filter_spec.objectSet = obj_specs
    filter_spec.propSet = [property_spec]
    pcfilter = property_collector.CreateFilter(filter_spec, True)
    try:
        version, state = None, None
        # Loop looking for updates till the state moves to a completed state.
        while len(task_list):
            update = property_collector.WaitForUpdates(version)
            for filter_set in update.filterSet:
                for obj_set in filter_set.objectSet:
                    task = obj_set.obj
                    for change in obj_set.changeSet:
                        if change.name == 'info':
                            state = change.val.state
                        elif change.name == 'info.state':
                            state = change.val
                        else:
                            continue

                        if not str(task) in task_list:
                            continue

                        if state == vim.TaskInfo.State.success:
                            # Remove task from taskList
                            task_list.remove(str(task))
                        elif state == vim.TaskInfo.State.error:
                            raise task.info.error
            # Move to next version
            version = update.version
    finally:
        if pcfilter:
            pcfilter.Destroy()


@contextmanager
def disconnecting(connection):
    try:
        yield connection
    finally:
        connect.Disconnect(connection)


class NotFound(Exception):
    pass


class Action(object):
    def __init__(self, si):
        self.si = si
        self.tasks = []

    def _find_obj(self, path):
        obj = self.si.content.searchIndex.FindByInventoryPath(path)
        if not obj:
            raise NotFound(str(path))
        return obj

    @abstractmethod
    def start(self):
        LOG.info("The action %s started.", self)
        return self

    def wait(self):
        if self.tasks:
            wait_for_tasks(self.si, self.tasks)
        LOG.info("The action %s have finished all the tasks.", self)

    def make_so(self):
        self.start().wait()


class CreateCluster(Action):
    def name(self, name):
        self.name = name
        return self

    def host_folder(self, path):
        self.host_folder = self._find_obj(path)
        return self

    def start(self):
        Action.start(self)
        self.host_folder.CreateCluster(self.name, vim.cluster.ConfigSpec())
        return self


class CloneVm(Action):
    def name(self, name):
        self.name = name
        return self

    def vm_folder_path(self, path):
        self.folder = self._find_obj(path)
        return self

    def source_path(self, path):
        self.source = self._find_obj(path)
        return self

    def resource_pool_path(self, path):
        self.resource_pool = self._find_obj(path)
        return self

    def to_template(self, to_template):
        self.to_template = to_template
        return self

    def start(self):
        Action.start(self)
        relocate_spec = vim.vm.CloneSpec(
            location=vim.vm.RelocateSpec(pool=self.resource_pool),
            template=self.to_template)
        self.tasks.append(self.source.Clone(
            self.folder, self.name, relocate_spec))
        return self


class CreateVm(Action):
    def __init__(self, si):
        Action.__init__(self, si)
        self.spec = vim.vm.ConfigSpec()
        self.spec.memoryMB = 512
        self.spec.cpuHotAddEnabled = True
        self.spec.deviceChange = []
        self.spec.guestId = "rhel6_64Guest"
        self._disk_no = 1
        self._disk_controller_no = 1

    def name(self, name):
        self.spec.name = name
        return self

    def placement(self, vm_folder_path, host_path, datastore_name):
        self.vm_folder_path(vm_folder_path)
        self.host_path(host_path)
        self.datastore_name(datastore_name)
        return self

    def vm_folder_path(self, path):
        self.vm_folder = self._find_obj(path)
        return self

    def host_path(self, path):
        self.host = self._find_obj(path)
        return self

    def datastore_name(self, name):
        self.datastore_name = name
        return self

    def start(self):
        Action.start(self)
        self.spec.files = vim.vm.FileInfo(
            vmPathName="[{datastore_name}] {name}".format(
                datastore_name=self.datastore_name,
                name=self.spec.name))
        self.tasks.append(self.vm_folder.CreateVm(
            config=self.spec, pool=self.host.resourcePool))
        return self

    def network(self, net_name, mac=None):
        device = vim.vm.device.VirtualVmxnet3()
        device.backing = (
            vim.vm.device.VirtualEthernetCard.NetworkBackingInfo())
        if mac:
            device.addressType = "manual"
            device.macAddress = str(mac)
        device.backing.deviceName = net_name
        self._add_dev(device)
        return self

    def disk(self, size):
        dev = vim.vm.device
        disk_uuid = uuid.uuid4()

        diskspec = dev.VirtualDisk(capacityInKB=int(size))
        diskspec.controllerKey = self._disk_controller_no
        diskspec.unitNumber = self._disk_no
        self._disk_no += 1
        diskspec.backing = dev.VirtualDisk.FlatVer2BackingInfo()
        diskspec.backing.diskMode = \
            vim.vm.device.VirtualDiskOption.DiskMode.persistent
        diskspec.backing.uuid = str(uuid)
        diskspec.backing.fileName = (
            '[{store}] {vm_name}/{disk_name}.vmdk'.format(
                store=self.datastore_name,
                vm_name=self.spec.name,
                disk_name="disk-{}".format(disk_uuid)))
        self._add_dev(diskspec).fileOperation = (
            dev.VirtualDeviceSpec.FileOperation.create)
        return self

    def scsi(self):
        vctl1 = vim.vm.device.ParaVirtualSCSIController()
        vctl1.key = 1
        vctl1.sharedBus = "noSharing"
        self._add_dev(vctl1)
        return self

    def _add_dev(self, device):
        spec = vim.vm.device.VirtualDeviceSpec()
        spec.device = device
        spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        self.spec.deviceChange.append(spec)
        return spec


class CreateHost(Action):
    ANY_THUMBPRINT = object()

    def __init__(self, si):
        super(CreateHost, self).__init__(si)
        self.spec = vim.host.ConnectSpec()

    def name(self, name):
        self.spec.hostName = name
        return self

    def creds(self, user, password):
        self.spec.userName = user
        self.spec.password = password
        return self

    def cluster_path(self, path):
        self.cluster = self._find_obj(path)
        return self

    def thumbprint(self, thumbprint):
        self.thumbprint = thumbprint
        return self

    def start(self):
        Action.start(self)
        if self.thumbprint is self.ANY_THUMBPRINT:
            self.spec.sslThumbprint = self.get_host_thumbprint()
            self.tasks.append(self.cluster.AddHost(self.spec, True))
        else:
            self.spec.sslThumbprint = self.thumbprint
            self.tasks.append(self.cluster.AddHost(self.spec, True))
        return self

    def get_host_thumbprint(self):
        task = self.cluster.AddHost(self.spec, True)
        while task.info.state == "running":
            sleep(1)
        if isinstance(task.info.error, vim.fault.SSLVerifyFault):
            thumbprint = task.info.error.thumbprint
            LOG.warning("Using thumbprint '{}' for host {} from non-secured "
                        "source.".format(thumbprint,
                                         self.spec.hostName))
            return thumbprint
        else:
            raise task.info.error


class DestroyEntity(Action):
    def path(self, path, must_exist=True):
        try:
            self.entity = self._find_obj(path)
        except NotFound:
            self.entity = None
            pass
        return self

    def start(self):
        Action.start(self)
        if self.entity:
            self.tasks.append(self.entity.Destroy())
        return self


class DestroyVM(DestroyEntity):
    def start(self):
        Action.start(self)
        if self.entity:
            self.tasks.append(self.entity.Destroy())
        return self


class DestroyHost(DestroyEntity):
    pass


class DisconnectHost(DestroyEntity):
    def start(self):
        Action.start(self)
        if self.entity:
            self.tasks.append(self.entity.Disconnect())
        return self


class DestroyCluster(DestroyEntity):
    def start(self):
        Action.start(self)
        if self.entity:
            self.entity.Destroy()
        return self
