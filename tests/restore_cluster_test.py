# -*- coding: utf-8 -*-
# Copyright 2019 Spotify AB. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import configparser
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import Mock

from medusa.config import (MedusaConfig, StorageConfig, _namedtuple_from_dict, CassandraConfig, GrpcConfig,
                           KubernetesConfig)
from medusa.restore_cluster import RestoreJob, expand_repeatable_option


class RestoreClusterTest(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setUp(self):
        config = configparser.ConfigParser(interpolation=None)
        config['storage'] = {
            'host_file_separator': ','
        }
        config['cassandra'] = {
            'config_file': os.path.join(os.path.dirname(__file__),
                                        'resources/yaml/work/cassandra_with_tokens_and_autobootstrap.yaml'),
            'start_cmd': '/etc/init.d/cassandra start',
            'stop_cmd': '/etc/init.d/cassandra stop',
            'is_ccm': '1',
            'resolve_ip_addresses': 'False'
        }
        config["grpc"] = {
            "enabled": "0"
        }
        config['kubernetes'] = {
            "enabled": "0"
        }
        self.config = config
        self.medusa_config = MedusaConfig(
            file_path=None,
            storage=_namedtuple_from_dict(StorageConfig, config['storage']),
            monitoring={},
            cassandra=_namedtuple_from_dict(CassandraConfig, config['cassandra']),
            ssh=None,
            checks=None,
            logging=None,
            grpc=_namedtuple_from_dict(GrpcConfig, config['grpc']),
            kubernetes=_namedtuple_from_dict(KubernetesConfig, config['kubernetes']),
        )
        self.tmp_dir = Path(tempfile.gettempdir())

    # Test that we can properly associate source and target nodes for restore using a host list
    def test_populate_ringmap(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            cluster_backup = Mock()
            tokenmap = json.loads(f.read())
            cluster_backup.tokenmap.return_value = tokenmap
            host_list = "tests/resources/restore_cluster_host_list.txt"
            restoreJob = RestoreJob(cluster_backup, self.medusa_config, self.tmp_dir, host_list, None, False, False,
                                    None)
            restoreJob._populate_hostmap()

        assert restoreJob.host_map["node1.mydomain.net"]['source'] == ["node1.mydomain.net"]
        assert restoreJob.host_map["node2.mydomain.net"]['source'] == ["node2.mydomain.net"]
        assert restoreJob.host_map["node3.mydomain.net"]['source'] == ["node4.mydomain.net"]

    # Test that we can properly associate source and target nodes for restore using a token map
    def test_populate_tokenmap(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            with open("tests/resources/restore_cluster_tokenmap.target.json", 'r') as f_target:
                tokenmap = json.loads(f.read())
                cluster_backup = MagicMock()
                restoreJob = RestoreJob(
                    cluster_backup,
                    self.medusa_config,
                    self.tmp_dir,
                    None,
                    "node1.mydomain.net",
                    False,
                    False,
                    None,
                    bypass_checks=True
                )

                target_tokenmap = json.loads(f_target.read())
                restoreJob._populate_ringmap(tokenmap, target_tokenmap)
                assert restoreJob.use_sstableloader is False

        assert restoreJob.host_map["node4.mydomain.net"]['source'] == ["node1.mydomain.net"]
        assert restoreJob.host_map["node5.mydomain.net"]['source'] == ["node2.mydomain.net"]
        assert restoreJob.host_map["node6.mydomain.net"]['source'] == ["node3.mydomain.net"]

    # Test that we can't restore the cluster if the source and target topology have different sizes
    def test_populate_tokenmap_fail(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            with open("tests/resources/restore_cluster_tokenmap.fail.json", 'r') as f_target:
                tokenmap = json.loads(f.read())
                cluster_backup = MagicMock()
                restoreJob = RestoreJob(
                    cluster_backup,
                    self.medusa_config,
                    self.tmp_dir,
                    None,
                    "node1.mydomain.net",
                    False,
                    False,
                    None,
                    bypass_checks=True
                )

                target_tokenmap = json.loads(f_target.read())
                restoreJob._populate_ringmap(tokenmap, target_tokenmap)
                # topologies are different, which forces the use of the sstableloader
                assert restoreJob.use_sstableloader is True

    # Test that we can't restore the cluster if the source and target topology have different tokens
    def test_populate_tokenmap_fail_tokens(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            with open("tests/resources/restore_cluster_tokenmap.fail_tokens.json", 'r') as f_target:
                tokenmap = json.loads(f.read())
                cluster_backup = MagicMock()
                restoreJob = RestoreJob(
                    cluster_backup, self.medusa_config, self.tmp_dir, None, "node1.mydomain.net", False, False, None
                )

                target_tokenmap = json.loads(f_target.read())
                restoreJob._populate_ringmap(tokenmap, target_tokenmap)
                # topologies are different, which forces the use of the sstableloader
                assert restoreJob.use_sstableloader is True

    def test_populate_ringmap_catches_mismatching_tokens_when_using_vnodes(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap_vnodes.json", 'r') as f:
            with open("tests/resources/restore_cluster_tokenmap_vnodes_target_fail.json", 'r') as f_target:
                tokenmap = json.loads(f.read())
                cluster_backup = MagicMock()
                restoreJob = RestoreJob(
                    cluster_backup, self.medusa_config, self.tmp_dir, None, "node1.mydomain.net", False, False, None
                )

                target_tokenmap = json.loads(f_target.read())
                restoreJob._populate_ringmap(tokenmap, target_tokenmap)
                # topologies are different, which forces the use of the sstableloader
                assert restoreJob.use_sstableloader is True

    def test_expand_repeatable_option(self):
        option, values = 'keyspace', {}
        result = expand_repeatable_option(option, values)
        assert result == ''

        option, values = 'keyspace', {'k1'}
        result = expand_repeatable_option(option, values)
        assert result == '--keyspace k1'

        option, values = 'keyspace', {'k1', 'k2'}
        result = expand_repeatable_option(option, sorted(list(values)))
        assert result == '--keyspace k1 --keyspace k2'

    def test_restore_is_in_place_no_diff(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            cluster_backup = Mock()
            tokenmap_content = f.read()
            tokenmap = json.loads(tokenmap_content)
            backup_tokenmap = json.loads(tokenmap_content)
            cluster_backup.tokenmap.return_value = tokenmap
            restoreJob = RestoreJob(cluster_backup, self.medusa_config, self.tmp_dir, None, None, False, False, None)
            in_place = restoreJob._is_restore_in_place(tokenmap, backup_tokenmap)
            assert in_place

    def test_restore_is_in_place_one_diff(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            with open("tests/resources/restore_cluster_tokenmap.one_changed.json", 'r') as f2:
                cluster_backup = Mock()
                tokenmap = json.loads(f2.read())
                backup_tokenmap = json.loads(f.read())
                cluster_backup.tokenmap.return_value = tokenmap
                restoreJob = RestoreJob(cluster_backup, self.medusa_config, self.tmp_dir, None, None, False, False,
                                        None)
                in_place = restoreJob._is_restore_in_place(tokenmap, backup_tokenmap)
                assert in_place

    def test_restore_is_not_in_place(self):
        node_backups = list()
        node_backups.append(Mock())
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            with open("tests/resources/restore_cluster_tokenmap.target.json", 'r') as f2:
                cluster_backup = Mock()
                tokenmap = json.loads(f2.read())
                backup_tokenmap = json.loads(f.read())
                cluster_backup.tokenmap.return_value = tokenmap
                restoreJob = RestoreJob(cluster_backup, self.medusa_config, self.tmp_dir, None, None, False, False,
                                        None)
                in_place = restoreJob._is_restore_in_place(tokenmap, backup_tokenmap)
                assert not in_place

    def test_cmd_no_config_specified(self):
        """Ensure that command line is OK when"""
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            cluster_backup = Mock()
            tokenmap = json.loads(f.read())
            cluster_backup.tokenmap.return_value = tokenmap
            host_list = "tests/resources/restore_cluster_host_list.txt"
            restore_job = RestoreJob(cluster_backup, self.medusa_config, self.tmp_dir, host_list, None, False, False,
                                     None)
            cmd = restore_job._build_restore_cmd()
            assert '--config-file' not in cmd

    def test_cmd_with_custom_config_path(self):
        with open("tests/resources/restore_cluster_tokenmap.json", 'r') as f:
            cluster_backup = Mock()
            tokenmap = json.loads(f.read())
            cluster_backup.tokenmap.return_value = tokenmap
            host_list = "tests/resources/restore_cluster_host_list.txt"
            config = MedusaConfig(
                file_path='/custom/path/to/medusa.ini',
                storage=_namedtuple_from_dict(StorageConfig, self.config['storage']),
                monitoring={},
                cassandra=_namedtuple_from_dict(CassandraConfig, self.config['cassandra']),
                ssh=None,
                checks=None,
                logging=None,
                grpc=_namedtuple_from_dict(GrpcConfig, self.config['grpc']),
                kubernetes=_namedtuple_from_dict(KubernetesConfig, self.config['kubernetes']),
            )
            restore_job = RestoreJob(cluster_backup, config, self.tmp_dir, host_list, None, False, False, None)
            cmd = restore_job._build_restore_cmd()
            assert '--config-file /custom/path/to/medusa.ini' in cmd


if __name__ == '__main__':
    unittest.main()
