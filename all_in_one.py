#!/usr/bin/python

# This module prepares the environment for testing OpenStack with VMWare
# Copyright (C) 2015  Jaroslav Henner
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

try:
    from oslo.config import cfg
except ImportError:
    from oslo_config import cfg

from pyVim import connect

import actions as ac

opts = [
    cfg.StrOpt('controller_vm_mac', required=True),
    cfg.StrOpt('controller_vm_memory'),
    cfg.StrOpt('tester_vm_mac', required=True),
    cfg.StrOpt('tester_vm_memory'),
    cfg.StrOpt('vm_folder_path', default='khaleesi'),
    cfg.StrOpt('vm_cluster_name', default='bar'),
    cfg.StrOpt('template_name', default="rhel-guest-image"),
    cfg.StrOpt('deployment_prefix', default=""),
    cfg.BoolOpt('workaround_pyvmomi_235', default=True,
                   help='Workaround '
                   'https://github.com/vmware/pyvmomi/issues/235'),
]

vcenter_opts = [
    cfg.StrOpt('host', required=True,
               help='The address of the vcenter.'),
    cfg.StrOpt('user', default='root'),
    cfg.StrOpt('password', required=True, secret=True),
]


CONF = cfg.ConfigOpts()
CONF.register_opts(opts)
CONF.register_opts(vcenter_opts, group="vcenter")

def state_present(si):
    controller_vm_name = "{}controller".format(CONF.deployment_prefix)
    tester_vm_name = "{}tester".format(CONF.deployment_prefix)

    with ac.BatchExecutor() as be:
        for name, mac, memory in ((controller_vm_name,
                                   CONF.controller_vm_mac,
                                   CONF.controller_vm_memory),
                                  (tester_vm_name,
                                   CONF.tester_vm_mac,
                                   CONF.tester_vm_memory)):
            be.submit(
                ac.CloneVm(si)
                .name(name)
                .to_template(False)
                ._mac(mac)
                ._memory(memory)
                .vm_folder_path("New Datacenter/vm/{}".format(
                    CONF.vm_folder_path))
                .source_path("New Datacenter/vm/{}".format(CONF.template_name))
                .resource_pool_path('New Datacenter/host/{}/Resources'.format(
                    CONF.vm_cluster_name))
            )
    with ac.BatchExecutor() as be:
        for name in (controller_vm_name, tester_vm_name):
            be.submit(ac.PowerOnVm(si).vm_path(
                "New Datacenter/vm/{}/{}".format(CONF.vm_folder_path, name)))


def state_absent(si):
    controller_vm_name = "{}controller".format(CONF.deployment_prefix)
    tester_vm_name = "{}tester".format(CONF.deployment_prefix)
    with ac.BatchExecutor() as be:
        for name in (controller_vm_name, tester_vm_name):
            be.submit(ac.PowerOffVm(si).vm_path(
                "New Datacenter/vm/{}/{}".format(CONF.vm_folder_path, name)))
    with ac.BatchExecutor() as be:
        for name in (controller_vm_name, tester_vm_name):
            be.submit(ac.DestroyVM(si).path(
                'New Datacenter/vm/{}/{}'.format(CONF.vm_folder_path, name),
                False)
            )


def add_actions(subparsers):
    subparsers.add_parser('present')
    subparsers.add_parser('absent')


def cli_main():
    import logging
    logging.basicConfig(level=logging.DEBUG)
    CONF.register_cli_opt(cfg.SubCommandOpt('action', handler=add_actions))
    CONF(project="vomit", prog="all-in-one")

    if CONF.workaround_pyvmomi_235:
        import ssl
        default_context = ssl._create_default_https_context
        ssl._create_default_https_context = ssl._create_unverified_context

    with ac.disconnecting(
        connect.SmartConnect(host=CONF.vcenter.host,
                             user=CONF.vcenter.user,
                             pwd=CONF.vcenter.password)) as si:
        if CONF.workaround_pyvmomi_235:
            ssl._create_default_https_context = default_context

        action = CONF.action.name
        globals().get("state_" + action)(si)


def list_opts():
    return [
        ['DEFAULT', opts],
        ['vcenter', vcenter_opts]
    ]
