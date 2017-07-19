from __future__ import absolute_import

from labrad.node import server_config as sc


class TestServerConfig(object):

    def test_parse_config(self):
        conf = sc.from_string("""
            [info]
            name = Python Test Server
            version = 1.2.3
            description = Basic python server.

            [startup]
            cmdline = %PYTHON% %FILE%
            timeout = 20

            [shutdown]
            message = 987654321
            timeout = 5
        """)
        assert conf.name == 'Python Test Server'
        assert conf.instance_name == conf.name
        assert conf.version == '1.2.3'
        assert conf.version_tuple == ((1, 2, 3), '1.2.3')
        assert conf.description == 'Basic python server.'

        assert conf.cmdline == '%PYTHON% %FILE%'
        assert conf.timeout == 20

        assert conf.shutdown_mode == ('message', 987654321)
        assert conf.shutdown_timeout == 5

    def test_parse_instance_name(self):
        conf = sc.from_string("""
            [info]
            name = Local Server
            instancename = %LABRADNODE% Local Server
            version = 1.2.3
            description = Basic python server.

            [startup]
            cmdline = %PYTHON% %FILE%
            timeout = 20

            [shutdown]
            message = 987654321
            timeout = 5
        """)
        assert conf.name == 'Local Server'
        assert conf.instance_name == '%LABRADNODE% Local Server'

    def test_parse_optional_version(self):
        conf = sc.from_string("""
            [info]
            name = Local Server
            description = Basic python server.

            [startup]
            cmdline = %PYTHON% %FILE%
            timeout = 20

            [shutdown]
            message = 987654321
            timeout = 5
        """)
        assert conf.version == '0.0'
        assert conf.version_tuple == ((0, 0), '0.0')

    def test_platform_specific_command_line(self):
        conf_str = """
            [info]
            name = Local Server
            description = Basic python server.

            [startup]
            cmdline = default_binary
            cmdline_win32 = windows_binary
            cmdline_linux2 = linux_binary
            timeout = 20

            [shutdown]
            message = 987654321
            timeout = 5
        """
        conf_win32 = sc.from_string(conf_str, platform='win32')
        assert conf_win32.cmdline == 'windows_binary'
        conf_linux2 = sc.from_string(conf_str, platform='linux2')
        assert conf_linux2.cmdline == 'linux_binary'
        conf_default = sc.from_string(conf_str, platform='osx')
        assert conf_default.cmdline == 'default_binary'


class TestVersionTuple(object):

    def test_version_tuple(self):
        assert sc.version_tuple('1') == ((1,), '1')
        assert sc.version_tuple('1.2') == ((1, 2), '1.2')
        assert sc.version_tuple('1.2.3') == ((1, 2, 3), '1.2.3')
        assert sc.version_tuple('1.2.3.4') == ((1, 2, 3, 4), '1.2.3.4')
        assert sc.version_tuple('1.2.3.4-dev') == ((1, 2, 3, 4), '1.2.3.4-dev')

    def test_version_tuple_on_malformed_versions(self):
        assert sc.version_tuple('version-a') == ((), 'version-a')

    def test_version_comparison(self):
        assert sc.version_tuple('1.2.3') > sc.version_tuple('1.2.2')
        assert sc.version_tuple('1.2.3') > sc.version_tuple('1.1.9')
        assert sc.version_tuple('1.2.3') > sc.version_tuple('1.0.8')
        assert sc.version_tuple('1.2.3') > sc.version_tuple('0.9.9')
        assert sc.version_tuple('1.10.0') > sc.version_tuple('1.9.9')
        assert sc.version_tuple('version-b') > sc.version_tuple('version-a')
