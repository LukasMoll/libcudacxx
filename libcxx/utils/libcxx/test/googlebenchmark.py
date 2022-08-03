from __future__ import absolute_import
import os
import subprocess
import sys

import lit.Test
import lit.TestRunner
import lit.util
from lit.formats.base import TestFormat

kIsWindows = sys.platform in ['win32', 'cygwin']


class GoogleBenchmark(TestFormat):
    def __init__(self, test_sub_dirs, test_suffix, benchmark_args=[]):
        self.benchmark_args = list(benchmark_args)
        self.test_sub_dirs = os.path.normcase(str(test_sub_dirs)).split(';')

        # On Windows, assume tests will also end in '.exe'.
        exe_suffix = str(test_suffix)
        if kIsWindows:
            exe_suffix += '.exe'

        # Also check for .py files for testing purposes.
        self.test_suffixes = {exe_suffix, test_suffix + '.py'}

    def get_benchmark_tests(self, path, lit_config, local_config):
        """getBenchmarkTests(path) - [name]

        Return the tests available in gtest executable.

        Args:
          path: String path to a gtest executable
          lit_config: LitConfig instance
          local_config: TestingConfig instance"""

        # TODO: allow splitting tests according to the "benchmark family" so
        # the output for a single family of tests all belongs to the same test
        # target.
        list_test_cmd = [path, '--benchmark_list_tests']
        try:
            output = subprocess.check_output(list_test_cmd,
                                             env=local_config.environment)
        except subprocess.CalledProcessError as exc:
            lit_config.warning(
                "unable to discover google-benchmarks in %r: %s. Process output: %s"
                % (path, sys.exc_info()[1], exc.output))
            raise StopIteration

        nested_tests = []
        for ln in output.splitlines(False):  # Don't keep newlines.
            ln = lit.util.to_string(ln)
            if not ln.strip():
                continue

            index = 0
            while ln[index * 2:index * 2 + 2] == '  ':
                index += 1
            while len(nested_tests) > index:
                nested_tests.pop()

            ln = ln[index * 2:]
            if ln.endswith('.'):
                nested_tests.append(ln)
            elif any([name.startswith('DISABLED_')
                      for name in nested_tests + [ln]]):
                # Gtest will internally skip these tests. No need to launch a
                # child process for it.
                continue
            else:
                yield ''.join(nested_tests) + ln

    def get_tests_in_directory(self, test_suite, path_in_suite,
                               lit_config, local_config):
        source_path = test_suite.getSourcePath(path_in_suite)
        for subdir in self.test_sub_dirs:
            dir_path = os.path.join(source_path, subdir)
            if not os.path.isdir(dir_path):
                continue
            for fn in lit.util.listdir_files(dir_path,
                                             suffixes=self.test_suffixes):
                # Discover the tests in this executable.
                execpath = os.path.join(source_path, subdir, fn)
                testnames = self.get_benchmark_tests(execpath, lit_config, local_config)
                for testname in testnames:
                    test_path = path_in_suite + (subdir, fn, testname)
                    yield lit.Test.Test(test_suite, test_path, local_config,
                                        file_path=execpath)

    def execute(self, test, lit_config):
        test_path, test_name = os.path.split(test.getSourcePath())
        while not os.path.exists(test_path):
            # Handle GTest parametrized and typed tests, whose name includes
            # some '/'s.
            test_path, name_prefix = os.path.split(test_path)
            test_name = name_prefix + '/' + test_name

        cmd = [test_path, '--benchmark_filter=%s$' % test_name] + self.benchmark_args

        if lit_config.noExecute:
            return lit.Test.PASS, ''

        try:
            out, err, exit_code = lit.util.execute_command(
                cmd, env=test.config.environment,
                timeout=lit_config.maxIndividualTestTime)
        except lit.util.ExecuteCommandTimeoutException:
            return (lit.Test.TIMEOUT,
                    'Reached timeout of {} seconds'.format(
                        lit_config.maxIndividualTestTime)
                    )

        if exit_code:
            return lit.Test.FAIL, ('exit code: %d\n' % exit_code) + out + err

        passing_test_line = test_name
        if passing_test_line not in out:
            msg = ('Unable to find %r in google benchmark output:\n\n%s%s' %
                   (passing_test_line, out, err))
            return lit.Test.UNRESOLVED, msg

        return lit.Test.PASS, err + out
