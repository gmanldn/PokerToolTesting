#!/usr/bin/env python3
"""
Final Test Validation and Health Check for Poker Assistant.
Comprehensive validation script that runs all tests and provides detailed reporting.

This script serves as the final validation before deployment or release.

Run with: python final_test_validation.py
"""

import sys
import os
import time
import json
import subprocess
import tempfile
import psutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_validation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Individual test result."""
    name: str
    passed: bool
    duration: float
    details: str = ""
    error_message: str = ""
    performance_metrics: Dict[str, Any] = None

    def __post_init__(self):
        if self.performance_metrics is None:
            self.performance_metrics = {}


@dataclass
class ValidationReport:
    """Complete validation report."""
    timestamp: str
    total_duration: float
    system_info: Dict[str, Any]
    test_results: List[TestResult]
    summary: Dict[str, Any]
    recommendations: List[str]


class TestValidator:
    """Main test validation orchestrator."""
    
    def __init__(self):
        self.start_time = time.time()
        self.test_results: List[TestResult] = []
        self.system_info = self._collect_system_info()
        
    def _collect_system_info(self) -> Dict[str, Any]:
        """Collect system information for the report."""
        try:
            return {
                'python_version': sys.version,
                'platform': sys.platform,
                'cpu_count': psutil.cpu_count(),
                'memory_total_gb': psutil.virtual_memory().total / (1024**3),
                'memory_available_gb': psutil.virtual_memory().available / (1024**3),
                'disk_free_gb': psutil.disk_usage('.').free / (1024**3),
                'working_directory': os.getcwd(),
                'test_files_present': self._check_test_files()
            }
        except Exception as e:
            logger.warning(f"Could not collect full system info: {e}")
            return {
                'python_version': sys.version,
                'platform': sys.platform,
                'working_directory': os.getcwd(),
                'error': str(e)
            }
    
    def _check_test_files(self) -> Dict[str, bool]:
        """Check which test files are present."""
        test_files = [
            'poker_test.py',
            'enhanced_poker_test.py',
            'additional_test_cases.py',
            'performance_benchmark_tests.py',
            'database_integrity_tests.py',
            'error_handling_tests.py',
            'gui_integration_tests.py',
            'security_validation_tests.py',
            'comprehensive_integration_tests.py',
            'poker_smoke.py',
            'run_all_tests.py',
            'test_config.py'
        ]
        
        return {file: Path(file).exists() for file in test_files}
    
    def _run_command(self, cmd: str, test_name: str, timeout: int = 300) -> TestResult:
        """Run a command and capture results."""
        logger.info(f"Running {test_name}...")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                return TestResult(
                    name=test_name,
                    passed=True,
                    duration=duration,
                    details=f"Completed successfully in {duration:.2f}s",
                    performance_metrics={'duration': duration}
                )
            else:
                return TestResult(
                    name=test_name,
                    passed=False,
                    duration=duration,
                    error_message=result.stderr,
                    details=f"Failed with return code {result.returncode}"
                )
                
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                name=test_name,
                passed=False,
                duration=duration,
                error_message="Test timed out",
                details=f"Timeout after {timeout}s"
            )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name=test_name,
                passed=False,
                duration=duration,
                error_message=str(e),
                details="Exception during execution"
            )
    
    def validate_environment(self) -> TestResult:
        """Validate the test environment."""
        logger.info("Validating test environment...")
        start_time = time.time()
        
        issues = []
        
        # Check Python version
        if sys.version_info < (3, 7):
            issues.append("Python 3.7+ required")
        
        # Check required modules
        required_modules = ['sqlite3', 'tkinter', 'random', 'threading']
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                issues.append(f"Missing required module: {module}")
        
        # Check poker modules
        try:
            import poker_modules
            import poker_init
        except ImportError as e:
            issues.append(f"Cannot import poker modules: {e}")
        
        # Check test files
        missing_files = [f for f, exists in self.system_info['test_files_present'].items() 
                        if not exists and f in ['poker_test.py', 'poker_smoke.py']]
        if missing_files:
            issues.append(f"Critical test files missing: {missing_files}")
        
        # Check available memory
        if self.system_info.get('memory_available_gb', 0) < 1:
            issues.append("Less than 1GB memory available")
        
        # Check disk space
        if self.system_info.get('disk_free_gb', 0) < 1:
            issues.append("Less than 1GB disk space available")
        
        duration = time.time() - start_time
        
        if issues:
            return TestResult(
                name="Environment Validation",
                passed=False,
                duration=duration,
                error_message="; ".join(issues),
                details=f"Found {len(issues)} environment issues"
            )
        else:
            return TestResult(
                name="Environment Validation",
                passed=True,
                duration=duration,
                details="Environment validation passed"
            )
    
    def run_core_tests(self) -> List[TestResult]:
        """Run core test suites."""
        results = []
        
        # Core unit tests
        if Path('poker_test.py').exists():
            result = self._run_command(
                f"{sys.executable} -m pytest poker_test.py -v --tb=short",
                "Core Unit Tests",
                timeout=120
            )
            results.append(result)
        
        # Enhanced tests
        if Path('enhanced_poker_test.py').exists():
            result = self._run_command(
                f"{sys.executable} -m pytest enhanced_poker_test.py -v --tb=short",
                "Enhanced Edge Case Tests",
                timeout=180
            )
            results.append(result)
        
        # Smoke tests
        if Path('poker_smoke.py').exists():
            result = self._run_command(
                f"{sys.executable} poker_smoke.py",
                "Smoke Tests",
                timeout=300
            )
            results.append(result)
        
        return results
    
    def run_specialized_tests(self) -> List[TestResult]:
        """Run specialized test suites."""
        results = []
        
        specialized_tests = [
            ('additional_test_cases.py', 'Additional Edge Cases', 60),
            ('performance_benchmark_tests.py', 'Performance Benchmarks', 300),
            ('database_integrity_tests.py', 'Database Integrity', 120),
            ('error_handling_tests.py', 'Error Handling', 120),
            ('gui_integration_tests.py', 'GUI Integration', 120),
            ('security_validation_tests.py', 'Security Validation', 120),
            ('comprehensive_integration_tests.py', 'Comprehensive Integration', 300),
        ]
        
        for test_file, test_name, timeout in specialized_tests:
            if Path(test_file).exists():
                if test_file == 'performance_benchmark_tests.py':
                    # Performance tests run directly
                    cmd = f"{sys.executable} {test_file}"
                else:
                    # Other tests run with pytest
                    cmd = f"{sys.executable} -m pytest {test_file} -v --tb=short"
                
                result = self._run_command(cmd, test_name, timeout)
                results.append(result)
        
        return results
    
    def run_performance_validation(self) -> TestResult:
        """Run performance validation."""
        logger.info("Running performance validation...")
        start_time = time.time()
        
        try:
            # Import and run basic performance check
            from test_config import BenchmarkSuite
            
            benchmark = BenchmarkSuite()
            
            # Quick performance tests
            hand_eval_results = benchmark.benchmark_hand_evaluation()
            
            # Check if performance meets expectations
            issues = []
            if hand_eval_results['mean'] > 0.005:  # 5ms threshold
                issues.append(f"Hand evaluation too slow: {hand_eval_results['mean']*1000:.1f}ms")
            
            if hand_eval_results['max'] > 0.05:  # 50ms threshold
                issues.append(f"Worst case hand evaluation too slow: {hand_eval_results['max']*1000:.1f}ms")
            
            duration = time.time() - start_time
            
            performance_metrics = {
                'hand_eval_mean_ms': hand_eval_results['mean'] * 1000,
                'hand_eval_max_ms': hand_eval_results['max'] * 1000,
                'duration': duration
            }
            
            if issues:
                return TestResult(
                    name="Performance Validation",
                    passed=False,
                    duration=duration,
                    error_message="; ".join(issues),
                    performance_metrics=performance_metrics
                )
            else:
                return TestResult(
                    name="Performance Validation",
                    passed=True,
                    duration=duration,
                    details=f"Hand evaluation: {hand_eval_results['mean']*1000:.2f}ms avg",
                    performance_metrics=performance_metrics
                )
                
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Performance Validation",
                passed=False,
                duration=duration,
                error_message=str(e),
                details="Exception during performance validation"
            )
    
    def run_coverage_analysis(self) -> TestResult:
        """Run coverage analysis if possible."""
        logger.info("Running coverage analysis...")
        start_time = time.time()
        
        try:
            # Check if coverage is available
            subprocess.run([sys.executable, "-c", "import coverage"], 
                          check=True, capture_output=True)
            
            # Run coverage
            result = self._run_command(
                f"{sys.executable} run_all_tests.py --coverage",
                "Coverage Analysis",
                timeout=600
            )
            
            return result
            
        except subprocess.CalledProcessError:
            duration = time.time() - start_time
            return TestResult(
                name="Coverage Analysis",
                passed=False,
                duration=duration,
                error_message="Coverage module not available",
                details="Install coverage with: pip install coverage"
            )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Coverage Analysis",
                passed=False,
                duration=duration,
                error_message=str(e),
                details="Exception during coverage analysis"
            )
    
    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        failed_tests = [r for r in self.test_results if not r.passed]
        slow_tests = [r for r in self.test_results if r.duration > 60]
        
        if failed_tests:
            recommendations.append(f"🔴 {len(failed_tests)} test(s) failed - review error messages and fix issues")
        
        if slow_tests:
            recommendations.append(f"⚠️ {len(slow_tests)} test(s) were slow (>60s) - consider optimization")
        
        # Check system resources
        if self.system_info.get('memory_available_gb', 0) < 2:
            recommendations.append("💾 Low memory available - close other applications")
        
        if self.system_info.get('cpu_count', 0) < 2:
            recommendations.append("🖥️ Limited CPU cores - tests may run slower")
        
        # Check test file coverage
        missing_files = [f for f, exists in self.system_info['test_files_present'].items() 
                        if not exists]
        if missing_files:
            recommendations.append(f"📁 Missing test files: {missing_files}")
        
        # Performance recommendations
        perf_tests = [r for r in self.test_results if 'Performance' in r.name and r.passed]
        if perf_tests:
            for test in perf_tests:
                if test.performance_metrics.get('hand_eval_mean_ms', 0) > 2:
                    recommendations.append("⚡ Hand evaluation performance could be improved")
        
        if not failed_tests and not slow_tests:
            recommendations.append("✅ All tests passed successfully - system is ready for deployment")
        
        return recommendations
    
    def generate_report(self) -> ValidationReport:
        """Generate comprehensive validation report."""
        total_duration = time.time() - self.start_time
        
        # Calculate summary statistics
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r.passed])
        failed_tests = total_tests - passed_tests
        
        summary = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            'total_duration': total_duration,
            'average_test_duration': total_duration / total_tests if total_tests > 0 else 0
        }
        
        recommendations = self.generate_recommendations()
        
        return ValidationReport(
            timestamp=datetime.now().isoformat(),
            total_duration=total_duration,
            system_info=self.system_info,
            test_results=self.test_results,
            summary=summary,
            recommendations=recommendations
        )
    
    def save_report(self, report: ValidationReport, filename: str = None):
        """Save report to file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"validation_report_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(asdict(report), f, indent=2)
        
        logger.info(f"Report saved to {filename}")
        return filename
    
    def print_summary(self, report: ValidationReport):
        """Print summary to console."""
        print("\n" + "="*80)
        print("🧪 POKER ASSISTANT - FINAL TEST VALIDATION REPORT")
        print("="*80)
        
        print(f"\n📊 SUMMARY")
        print(f"   Total Tests: {report.summary['total_tests']}")
        print(f"   Passed: {report.summary['passed_tests']}")
        print(f"   Failed: {report.summary['failed_tests']}")
        print(f"   Success Rate: {report.summary['success_rate']:.1f}%")
        print(f"   Total Duration: {report.total_duration:.1f}s")
        
        print(f"\n🖥️  SYSTEM INFO")
        print(f"   Python: {report.system_info['python_version'].split()[0]}")
        print(f"   Platform: {report.system_info['platform']}")
        print(f"   CPU Cores: {report.system_info.get('cpu_count', 'Unknown')}")
        print(f"   Memory: {report.system_info.get('memory_available_gb', 0):.1f}GB available")
        
        print(f"\n📋 TEST RESULTS")
        for result in report.test_results:
            status = "✅" if result.passed else "❌"
            print(f"   {status} {result.name:<30} {result.duration:>6.1f}s")
            if not result.passed and result.error_message:
                print(f"      Error: {result.error_message[:80]}...")
        
        print(f"\n💡 RECOMMENDATIONS")
        for rec in report.recommendations:
            print(f"   {rec}")
        
        if report.summary['failed_tests'] == 0:
            print(f"\n🎉 SUCCESS: All tests passed! Poker Assistant is ready for deployment.")
        else:
            print(f"\n⚠️  WARNING: {report.summary['failed_tests']} test(s) failed. Review and fix before deployment.")
        
        print("="*80)
    
    def run_full_validation(self) -> ValidationReport:
        """Run complete validation suite."""
        logger.info("Starting full test validation...")
        
        # Environment validation
        env_result = self.validate_environment()
        self.test_results.append(env_result)
        
        if not env_result.passed:
            logger.error("Environment validation failed - aborting")
            return self.generate_report()
        
        # Core tests
        core_results = self.run_core_tests()
        self.test_results.extend(core_results)
        
        # Specialized tests
        specialized_results = self.run_specialized_tests()
        self.test_results.extend(specialized_results)
        
        # Performance validation
        perf_result = self.run_performance_validation()
        self.test_results.append(perf_result)
        
        # Coverage analysis (optional)
        coverage_result = self.run_coverage_analysis()
        self.test_results.append(coverage_result)
        
        # Generate final report
        report = self.generate_report()
        
        return report


def main():
    """Main validation entry point."""
    print("🧪 Poker Assistant - Final Test Validation")
    print("=" * 50)
    
    validator = TestValidator()
    
    try:
        report = validator.run_full_validation()
        
        # Print summary
        validator.print_summary(report)
        
        # Save detailed report
        report_file = validator.save_report(report)
        print(f"\n📄 Detailed report saved to: {report_file}")
        
        # Exit with appropriate code
        if report.summary['failed_tests'] == 0:
            sys.exit(0)  # Success
        else:
            sys.exit(1)  # Failure
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Validation interrupted by user")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Validation failed with exception: {e}")
        print(f"\n❌ Validation failed: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()
