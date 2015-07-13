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

from oslo.config import cfg
from pyVim import connect

import actions as ac

opts = [
    cfg.StrOpt('vcenter_host', required=True,
               help='The address of the vcenter.'),
    cfg.StrOpt('vcenter_user', default='root'),
    cfg.StrOpt('vcenter_password', required=True, secret=True),
    cfg.StrOpt('controller_vm_name', default='controller'),
    cfg.StrOpt('controller_vm_mac', required=True),
    cfg.StrOpt('tester_vm_name', default='tester'),
    cfg.StrOpt('tester_vm_mac', required=True),
    cfg.StrOpt('vm_folder_path', default='khaleesi'),
    cfg.StrOpt('vm_cluster_name', default='bar'),
    cfg.StrOpt('template_name', default="rhel-guest-image"),
]

CONF = cfg.ConfigOpts()
CONF.register_opts(opts)


def state_present(si):
    with ac.BatchExecutor() as be:
        for name, mac in ((CONF.controller_vm_name, CONF.controller_vm_mac),
                          (CONF.tester_vm_name, CONF.tester_vm_mac)):
            be.submit(
                ac.CloneVm(si)
                .name(name)
                .to_template(False)
                ._mac(mac)
                .vm_folder_path("New Datacenter/vm/{}".format(
                    CONF.vm_folder_path))
                .source_path("New Datacenter/vm/{}".format(CONF.template_name))
                .resource_pool_path('New Datacenter/host/{}/Resources'.format(
                    CONF.vm_cluster_name))
            )
    with ac.BatchExecutor() as be:
        for name in (CONF.controller_vm_name, CONF.tester_vm_name):
            be.submit(ac.PowerOnVm(si).vm_path(
                "New Datacenter/vm/{}/{}".format(CONF.vm_folder_path, name)))


def state_absent(si):
    with ac.BatchExecutor() as be:
        for name in (CONF.controller_vm_name, CONF.tester_vm_name):
            be.submit(ac.PowerOffVm(si).vm_path(
                "New Datacenter/vm/{}/{}".format(CONF.vm_folder_path, name)))
    with ac.BatchExecutor() as be:
        for name in (CONF.controller_vm_name, CONF.tester_vm_name):
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
    CONF(project="ansible_pyvmomi", prog="all-in-one")
    with ac.disconnecting(
        connect.SmartConnect(host=CONF.vcenter_host,
                             user=CONF.vcenter_user,
                             pwd=CONF.vcenter_password)) as si:

        action = CONF.action.name
        globals().get("state_" + action)(si)


def list_opts():
    return [['DEFAULT', opts]]
