#!/usr/bin/env python3

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

"""
Custom test runner that tracks and reports skipped tests.
"""

import sys
import unittest
import argparse
from io import StringIO


class SkippedTestTracker(unittest.TextTestResult):
    """Custom test result that tracks skipped tests with their reasons."""
    
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.skipped_tests = []
    
    def addSkip(self, test, reason):
        """Override to track skipped tests."""
        super().addSkip(test, reason)
        self.skipped_tests.append({
            'test': str(test),
            'reason': reason,
            'class': test.__class__.__name__,
            'method': test._testMethodName
        })


class SkippedTestRunner(unittest.TextTestRunner):
    """Custom test runner that uses our SkippedTestTracker."""
    
    def __init__(self, stream=None, descriptions=True, verbosity=1, 
                 failfast=False, buffer=False, resultclass=None, warnings=None, *, tb_locals=False):
        if resultclass is None:
            resultclass = SkippedTestTracker
        super().__init__(stream, descriptions, verbosity, failfast, buffer, 
                         resultclass, warnings, tb_locals=tb_locals)
    
    def run(self, test):
        """Run tests and report skipped tests at the end."""
        result = super().run(test)
        
        # Print summary of skipped tests
        if hasattr(result, 'skipped_tests') and result.skipped_tests:
            self.stream.write('\n' + '='*70 + '\n')
            self.stream.write(f'SKIPPED TESTS SUMMARY ({len(result.skipped_tests)} total)\n')
            self.stream.write('='*70 + '\n')
            
            # Group by class for better organization
            by_class = {}
            for skip in result.skipped_tests:
                class_name = skip['class']
                if class_name not in by_class:
                    by_class[class_name] = []
                by_class[class_name].append(skip)
            
            for class_name, skips in sorted(by_class.items()):
                self.stream.write(f'\n{class_name}:\n')
                for skip in skips:
                    self.stream.write(f'  - {skip["method"]}: {skip["reason"]}\n')
            
            self.stream.write('\n' + '='*70 + '\n')
        else:
            self.stream.write('\nNo tests were skipped.\n')
        
        return result


def main():
    """Main entry point for the custom test runner."""
    parser = argparse.ArgumentParser(description='Run tests with skipped test tracking')
    parser.add_argument('--start-directory', '-s', default='test', 
                       help='Directory to start discovery (default: test)')
    parser.add_argument('--pattern', '-p', default='test*.py',
                       help='Pattern to match test files (default: test*.py)')
    parser.add_argument('--top-level-directory', '-t', default=None,
                       help='Top level directory of project')
    parser.add_argument('--verbose', '-v', action='count', default=1,
                       help='Verbose output (can be used multiple times)')
    parser.add_argument('--failfast', '-f', action='store_true',
                       help='Stop on first failure')
    parser.add_argument('--buffer', '-b', action='store_true',
                       help='Buffer stdout and stderr during tests')
    
    args = parser.parse_args()
    
    # Discover tests
    loader = unittest.TestLoader()
    
    try:
        suite = loader.discover(
            start_dir=args.start_directory,
            pattern=args.pattern,
            top_level_dir=args.top_level_directory
        )
    except ImportError as e:
        print(f"Error discovering tests: {e}")
        return 1
    
    # Run tests with our custom runner
    runner = SkippedTestRunner(
        verbosity=args.verbose,
        failfast=args.failfast,
        buffer=args.buffer
    )
    
    result = runner.run(suite)
    
    # Return appropriate exit code
    if result.wasSuccessful():
        return 0
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
