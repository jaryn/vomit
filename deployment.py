#!/usr/bin/python

# Copyright (C) 2015  Jaroslav Henner
#
# This file is part of pyvmomi ansible module.
#
# pyvmomi ansible module is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# pyvmomi ansible module is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyvmomi ansible more.  If not, see <http://www.gnu.org/licenses/>.

from oslo.config import cfg
from pyVim import connect

import actions as ac

opts = [
    cfg.StrOpt('vcenter_host', required=True,
               help='The address of the vcenter.'),
    cfg.StrOpt('vcenter_user', default='root'),
    cfg.StrOpt('vcenter_password', required=True, secret=True),
    cfg.StrOpt('esxi_host_address', required=True),
    cfg.StrOpt('esxi_host_username', required=True),
    cfg.StrOpt('esxi_host_password', required=True, secret=True),
    cfg.StrOpt('esxi_datastore_name', default='datastore1'),
    cfg.StrOpt('esxi_cluster_name', default='test'),
    cfg.StrOpt('vm_name', default='test'),
    cfg.StrOpt('vm_cluster_name', default='foo'),
    cfg.StrOpt('template_name', default="rhel-guest-image-template2")
]

CONF = cfg.ConfigOpts()
CONF.register_opts(opts)


def state_present(si):
    ac.CreateCluster(si)\
        .name(CONF.esxi_cluster_name)\
        .host_folder('New Datacenter/host')\
        .make_so()

    ac.CreateHost(si)\
        .name(CONF.esxi_host_address)\
        .cluster_path('New Datacenter/host/{}'.format(CONF.esxi_cluster_name))\
        .creds(CONF.esxi_host_username, CONF.esxi_host_password)\
        .thumbprint(ac.CreateHost.ANY_THUMBPRINT)\
        .make_so()

    ac.CreateVm(si).name(CONF.vm_name)\
        .vm_folder_path('New Datacenter/vm/')\
        .host_path('New Datacenter/host/{}'.format(CONF.vm_cluster_name))\
        .datastore_name(CONF.esxi_datastore_name)\
        .network('br100', "11:22:33:44:55:66")\
        .disk(1e6)\
        .disk(2e6)\
        .scsi()\
        .make_so()

    ac.CloneVm(si)\
        .name(CONF.vm_name + "_from_template")\
        .to_template(False)\
        .vm_folder_path("New Datacenter/vm")\
        .source_path("New Datacenter/vm/{}".format(CONF.template_name))\
        .resource_pool_path('New Datacenter/host/{}/Resources'.format(
            CONF.vm_cluster_name))\
        .make_so()


def state_absent(si):
    ac.DestroyVM(si).path(
        'New Datacenter/vm/{}'.format(CONF.vm_name), False).make_so()
    ac.DestroyVM(si).path(
        'New Datacenter/vm/{}'.format(CONF.vm_name + '_from_template'), False) \
        .make_so()
    ac.DisconnectHost(si).path(
        'New Datacenter/host/{}/{}'.format(
            CONF.esxi_cluster_name, CONF.esxi_host_address), False).make_so()
    ac.DestroyHost(si).path(
        'New Datacenter/host/{}/{}'.format(
            CONF.esxi_cluster_name, CONF.esxi_host_address), False).make_so()
    ac.DestroyCluster(si).path('New Datacenter/host/{}'.format(
        CONF.esxi_cluster_name), False).make_so()


def add_actions(subparsers):
    subparsers.add_parser('present')
    subparsers.add_parser('absent')


def cli_main():
    import logging
    logging.basicConfig(level=logging.DEBUG)
    CONF.register_cli_opt(cfg.SubCommandOpt('action', handler=add_actions))
    CONF(project="ansible_pyvmomi", prog="deployment")
    with ac.disconnecting(
        connect.SmartConnect(host=CONF.vcenter_host,
                             user=CONF.vcenter_user,
                             pwd=CONF.vcenter_password)) as si:

        action = CONF.action.name
        globals().get("state_" + action)(si)
