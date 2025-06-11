#!/usr/bin/env python3
"""
Comprehensive thread configuration testing script.

This script tests the vectorset-hnsw-max-threads configuration by:
1. Starting Redis servers with different thread configurations
2. Running the threads_config.py test against each configuration
3. Collecting results and identifying bugs/issues

Usage:
    python3 test_all_thread_configs.py [--configs 0,1,4,8,16,32,64]
"""

import subprocess
import time
import signal
import os
import sys
import argparse
import tempfile
import shutil
from pathlib import Path


class RedisServerManager:
    """Manages Redis server instances with different configurations"""

    def __init__(self, redis_executable="redis-server"):
        self.redis_executable = redis_executable
        self.server_process = None
        self.config_file = None
        self.port = 6379

    def create_config_file(self, threads_config, port=6379):
        """Create a temporary Redis config file with specific thread configuration"""
        config_content = f"""
# Redis configuration for vectorset-hnsw-max-threads testing
port {port}
bind 127.0.0.1
save ""
appendonly no
enable-debug-command yes

# Set vector-sets thread configuration
vectorset-hnsw-max-threads {threads_config}
"""

        # Create temporary config file
        fd, config_path = tempfile.mkstemp(suffix='.conf', prefix='redis_threads_')
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)

        self.config_file = config_path
        self.port = port
        return config_path

    def start_server(self, threads_config, port=6379, timeout=10):
        """Start Redis server with specific thread configuration"""
        config_path = self.create_config_file(threads_config, port)

        print(f"🚀 Starting Redis server with {threads_config} threads on port {port}...")
        print(f"   Config file: {config_path}")

        try:
            # Start Redis server
            self.server_process = subprocess.Popen(
                [self.redis_executable, config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group
            )

            # Wait for server to start
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.server_process.poll() is not None:
                    # Process has terminated
                    stdout, stderr = self.server_process.communicate()
                    print(f"❌ Redis server failed to start:")
                    print(f"   stdout: {stdout.decode()}")
                    print(f"   stderr: {stderr.decode()}")
                    return False

                # Test connection
                try:
                    result = subprocess.run(
                        ['redis-cli', '-p', str(port), 'ping'],
                        capture_output=True,
                        timeout=1
                    )
                    if result.returncode == 0 and b'PONG' in result.stdout:
                        print(f"✅ Redis server started successfully on port {port}")
                        return True
                except subprocess.TimeoutExpired:
                    pass

                time.sleep(0.5)

            print(f"❌ Redis server failed to start within {timeout} seconds")
            return False

        except Exception as e:
            print(f"❌ Error starting Redis server: {e}")
            return False

    def stop_server(self):
        """Stop the Redis server"""
        if self.server_process:
            print(f"🛑 Stopping Redis server (PID: {self.server_process.pid})...")

            try:
                # Send SIGTERM to the process group
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGTERM)

                # Wait for graceful shutdown
                try:
                    self.server_process.wait(timeout=5)
                    print("✅ Redis server stopped gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    print("⚠️  Forcing Redis server shutdown...")
                    os.killpg(os.getpgid(self.server_process.pid), signal.SIGKILL)
                    self.server_process.wait()
                    print("✅ Redis server force-stopped")

            except ProcessLookupError:
                print("✅ Redis server already stopped")
            except Exception as e:
                print(f"⚠️  Error stopping Redis server: {e}")

            self.server_process = None

        # Clean up config file
        if self.config_file and os.path.exists(self.config_file):
            os.unlink(self.config_file)
            self.config_file = None

    def __del__(self):
        """Cleanup on destruction"""
        self.stop_server()


def run_threads_config_test(port=6379):
    """Run the threads_config.py test against a specific Redis instance"""
    print(f"🧪 Running threads_config.py test against port {port}...")

    try:
        result = subprocess.run(
            ['python3', 'test.py', '--test', 'threads_config', '--primary-port', str(port)],
            capture_output=True,
            text=True,
            timeout=60  # 1 minute timeout
        )

        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }

    except subprocess.TimeoutExpired:
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': 'Test timed out after 60 seconds',
            'success': False
        }
    except Exception as e:
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': f'Error running test: {e}',
            'success': False
        }


def test_thread_configuration(threads_config, redis_manager, port=6379):
    """Test a specific thread configuration"""
    print(f"\n{'='*70}")
    print(f"TESTING CONFIGURATION: vectorset-hnsw-max-threads = {threads_config}")
    print(f"{'='*70}")

    # Start Redis server with specific configuration
    if not redis_manager.start_server(threads_config, port):
        return {
            'threads': threads_config,
            'server_started': False,
            'test_result': None,
            'summary': 'Failed to start Redis server'
        }

    # Wait a moment for server to fully initialize
    time.sleep(2)

    # Run the test
    test_result = run_threads_config_test(port)

    # Stop the server
    redis_manager.stop_server()

    # Analyze results
    summary = analyze_test_result(threads_config, test_result)

    return {
        'threads': threads_config,
        'server_started': True,
        'test_result': test_result,
        'summary': summary
    }


def analyze_test_result(threads_config, test_result):
    """Analyze test results and provide summary"""
    if not test_result['success']:
        if 'Connection refused' in test_result['stderr']:
            return f"❌ CRASH: Redis crashed during test (threads={threads_config})"
        elif 'timed out' in test_result['stderr']:
            return f"⏰ TIMEOUT: Test timed out (threads={threads_config})"
        else:
            return f"❌ FAILED: Test failed (threads={threads_config})"
    else:
        # Check for specific log messages in stdout
        stdout = test_result['stdout']
        if 'CAS option disabled' in stdout:
            return f"✅ SUCCESS: CAS disabled log found (threads={threads_config},{stdout})"
        else:
            return f"✅ SUCCESS: Test passed (threads={threads_config})"


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Test all thread configurations')
    parser.add_argument('--configs', default='0,1,4,8,16,32,64',
                       help='Comma-separated list of thread configs to test')
    parser.add_argument('--port', type=int, default=6379,
                       help='Redis port to use (default: 6379)')
    parser.add_argument('--redis-server', default='redis-server',
                       help='Redis server executable path')

    args = parser.parse_args()

    # Parse thread configurations
    try:
        thread_configs = [int(x.strip()) for x in args.configs.split(',')]
    except ValueError:
        print("❌ Error: Invalid thread configurations. Use comma-separated integers.")
        sys.exit(1)

    print("🧪 Redis Vector-Sets Thread Configuration Tester")
    print("=" * 60)
    print(f"Thread configurations to test: {thread_configs}")
    print(f"Redis server: {args.redis_server}")
    print(f"Test port: {args.port}")

    # Initialize Redis manager
    redis_manager = RedisServerManager(args.redis_server)

    # Test each configuration
    results = []

    try:
        for threads_config in thread_configs:
            result = test_thread_configuration(threads_config, redis_manager, args.port)
            results.append(result)

            # Print immediate result
            print(f"\n📊 Result: {result['summary']}")

            # Wait between tests
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n⚠️  Testing interrupted by user")
        redis_manager.stop_server()
        sys.exit(1)

    # Print final summary
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}")

    for result in results:
        threads = result['threads']
        summary = result['summary']
        print(f"  {threads:2d} threads: {summary}")

    # Count results
    crashed = sum(1 for r in results if 'CRASH' in r['summary'])
    failed = sum(1 for r in results if 'FAILED' in r['summary'])
    success = sum(1 for r in results if 'SUCCESS' in r['summary'])

    print(f"\n📈 Statistics:")
    print(f"  ✅ Successful: {success}")
    print(f"  ❌ Failed: {failed}")
    print(f"  💥 Crashed: {crashed}")
    print(f"  📊 Total: {len(results)}")

    if crashed > 0:
        print(f"\n⚠️  WARNING: {crashed} configuration(s) caused Redis to crash!")
        print("This indicates bugs in the vector-sets module that need to be fixed.")


def check_prerequisites():
    """Check if all prerequisites are available"""
    issues = []

    # Check if redis-server is available
    try:
        result = subprocess.run(['redis-server', '--version'],
                              capture_output=True, timeout=5)
        if result.returncode != 0:
            issues.append("redis-server not found or not working")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        issues.append("redis-server not found in PATH")

    # Check if redis-cli is available
    try:
        result = subprocess.run(['redis-cli', '--version'],
                              capture_output=True, timeout=5)
        if result.returncode != 0:
            issues.append("redis-cli not found or not working")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        issues.append("redis-cli not found in PATH")

    # Check if test.py exists
    if not os.path.exists('test.py'):
        issues.append("test.py not found in current directory")

    # Check if threads_config.py test exists
    if not os.path.exists('tests/threads_config.py'):
        issues.append("tests/threads_config.py not found")

    return issues


def print_usage_examples():
    """Print usage examples"""
    print("\n💡 Usage Examples:")
    print("  # Test all default configurations:")
    print("  python3 test_all_thread_configs.py")
    print("")
    print("  # Test specific configurations:")
    print("  python3 test_all_thread_configs.py --configs 0,1,32")
    print("")
    print("  # Use custom Redis server:")
    print("  python3 test_all_thread_configs.py --redis-server /usr/local/bin/redis-server")
    print("")
    print("  # Test on different port:")
    print("  python3 test_all_thread_configs.py --port 6380")


if __name__ == "__main__":
    # Check prerequisites first
    issues = check_prerequisites()
    if issues:
        print("❌ Prerequisites check failed:")
        for issue in issues:
            print(f"   - {issue}")
        print_usage_examples()
        sys.exit(1)

    main()
