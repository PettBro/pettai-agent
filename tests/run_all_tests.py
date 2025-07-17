#!/usr/bin/env python3
"""
Main test runner for the pett_agent project.
Runs unit, integration, and end-to-end tests.
"""

import asyncio
import logging
import sys
import os
import argparse
from typing import List, Tuple

# Add the parent directory to the path so we can import test modules
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_unit_tests() -> bool:
    """Run all unit tests."""
    try:
        from unit.test_pett_tools import (
            test_pett_tools_creation,
            test_pett_tools_validation,
        )

        logger.info("🧪 Running Unit Tests")
        logger.info("=" * 30)

        tests = [
            ("PettTools Creation", test_pett_tools_creation),
            ("PettTools Validation", test_pett_tools_validation),
        ]

        results = []
        for test_name, test_func in tests:
            logger.info(f"\n🔍 Running {test_name}...")
            try:
                await test_func()
                results.append((test_name, True))
                logger.info(f"✅ {test_name} passed!")
            except Exception as e:
                logger.error(f"❌ {test_name} failed: {e}")
                results.append((test_name, False))

        passed = sum(1 for _, result in results if result)
        logger.info(f"\n🎯 Unit Tests: {passed}/{len(results)} passed")

        return passed == len(results)

    except Exception as e:
        logger.error(f"❌ Error running unit tests: {e}")
        return False


async def run_integration_tests() -> bool:
    """Run all integration tests."""
    try:
        from integration.test_websocket_client import run_integration_tests

        logger.info("🧪 Running Integration Tests")
        logger.info("=" * 30)

        result = await run_integration_tests()
        return result

    except Exception as e:
        logger.error(f"❌ Error running integration tests: {e}")
        return False


async def run_e2e_tests() -> bool:
    """Run all end-to-end tests."""
    try:
        from e2e.test_ai_search import run_e2e_tests

        logger.info("🧪 Running End-to-End Tests")
        logger.info("=" * 30)

        result = await run_e2e_tests()
        return result

    except Exception as e:
        logger.error(f"❌ Error running e2e tests: {e}")
        return False


async def run_all_tests() -> Tuple[bool, dict]:
    """Run all tests and return results."""
    logger.info("🚀 Running All Tests")
    logger.info("=" * 50)

    test_suites = [
        ("Unit Tests", run_unit_tests),
        ("Integration Tests", run_integration_tests),
        ("End-to-End Tests", run_e2e_tests),
    ]

    results = {}
    all_passed = True

    for suite_name, suite_func in test_suites:
        logger.info(f"\n{'='*20} {suite_name} {'='*20}")
        try:
            result = await suite_func()
            results[suite_name] = result
            if not result:
                all_passed = False
        except Exception as e:
            logger.error(f"❌ Error running {suite_name}: {e}")
            results[suite_name] = False
            all_passed = False

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 Final Test Results:")
    logger.info("=" * 50)

    total_passed = 0
    total_suites = len(results)

    for suite_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{suite_name}: {status}")
        if result:
            total_passed += 1

    logger.info(f"\n🎯 Overall: {total_passed}/{total_suites} test suites passed")

    if all_passed:
        logger.info("🎉 All tests passed!")
    else:
        logger.error("❌ Some tests failed!")

    return all_passed, results


def main():
    """Main function to run tests based on command line arguments."""
    parser = argparse.ArgumentParser(description="Run pett_agent tests")
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "e2e", "all"],
        default="all",
        help="Type of tests to run (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("🧪 Pett Agent Test Suite")
    logger.info("=" * 30)

    if args.type == "unit":
        success = asyncio.run(run_unit_tests())
    elif args.type == "integration":
        success = asyncio.run(run_integration_tests())
    elif args.type == "e2e":
        success = asyncio.run(run_e2e_tests())
    else:  # all
        success, _ = asyncio.run(run_all_tests())

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
