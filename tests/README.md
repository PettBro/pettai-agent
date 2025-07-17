# Pett Agent Test Suite

This directory contains the comprehensive test suite for the Pett Agent project, organized by test type and functionality.

## 📁 Directory Structure

```
tests/
├── __init__.py                 # Makes tests a Python package
├── README.md                   # This file
├── run_all_tests.py           # Main test runner
├── unit/                      # Unit tests
│   ├── __init__.py
│   └── test_pett_tools.py     # Tests for PettTools class
├── integration/               # Integration tests
│   ├── __init__.py
│   └── test_websocket_client.py # Tests for WebSocket client
└── e2e/                       # End-to-end tests
    ├── __init__.py
    └── test_ai_search.py      # Tests for AI search functionality
```

## 🧪 Test Categories

### Unit Tests (`unit/`)

- **Purpose**: Test individual components in isolation
- **Scope**: Single functions, classes, or methods
- **Dependencies**: Minimal external dependencies
- **Speed**: Fast execution
- **Examples**:
  - PettTools creation and validation
  - Input validation
  - Error handling

### Integration Tests (`integration/`)

- **Purpose**: Test how components work together
- **Scope**: Multiple components interacting
- **Dependencies**: External services (WebSocket server)
- **Speed**: Medium execution time
- **Examples**:
  - WebSocket connection and authentication
  - Pet actions and responses
  - Message handling

### End-to-End Tests (`e2e/`)

- **Purpose**: Test complete user workflows
- **Scope**: Full application functionality
- **Dependencies**: All external services
- **Speed**: Slower execution
- **Examples**:
  - Complete AI search flow
  - Timeout handling
  - Error scenarios

## 🚀 Running Tests

### Prerequisites

1. **Environment Setup**: Make sure you have the required environment variables:

   ```bash
   export PRIVY_TOKEN="your_privy_token_here"
   ```

2. **Dependencies**: Install all project dependencies:
   ```bash
   poetry install
   # or
   pip install -r requirements.txt
   ```

### Running All Tests

```bash
# Run all tests
python tests/run_all_tests.py

# Run with verbose output
python tests/run_all_tests.py --verbose
```

### Running Specific Test Categories

```bash
# Run only unit tests
python tests/run_all_tests.py --type unit

# Run only integration tests
python tests/run_all_tests.py --type integration

# Run only end-to-end tests
python tests/run_all_tests.py --type e2e
```

### Running Individual Test Files

```bash
# Unit tests
python tests/unit/test_pett_tools.py

# Integration tests
python tests/integration/test_websocket_client.py

# End-to-end tests
python tests/e2e/test_ai_search.py
```

## 📊 Test Results

Tests provide detailed logging output with:

- ✅ Success indicators
- ❌ Error indicators
- 📊 Summary statistics
- 🔍 Detailed test progress
- ⏰ Timing information

### Example Output

```
🧪 Pett Agent Test Suite
==============================
🚀 Running All Tests
==================================================

==================== Unit Tests ====================
🔍 Running PettTools Creation...
✅ PettTools Creation passed!
🔍 Running PettTools Validation...
✅ PettTools Validation passed!
🎯 Unit Tests: 2/2 passed

================== Integration Tests ==================
🔌 Testing WebSocket connection...
✅ WebSocket connection established
✅ WebSocket connection closed
✅ WebSocket Connection test passed!
🔐 Authenticating with Privy token...
✅ Authentication successful!
✅ Privy Authentication test passed!
🎾 Testing pet actions...
✅ Pet Actions test passed!
🎯 Integration Tests: 3/3 passed

================== End-to-End Tests ==================
🔍 Testing AI search with prompt: 'What is the latest news about artificial intelligence?'
✅ AI search test passed!
🎯 End-to-End Tests: 1/1 passed

==================================================
📊 Final Test Results:
==================================================
Unit Tests: ✅ PASSED
Integration Tests: ✅ PASSED
End-to-End Tests: ✅ PASSED

🎯 Overall: 3/3 test suites passed
🎉 All tests passed!
```

## 🔧 Test Configuration

### Environment Variables

- `PRIVY_TOKEN`: Required for authentication tests
- `LOG_LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)

### Test Timeouts

- **Unit Tests**: No timeout (fast execution)
- **Integration Tests**: 30 seconds for authentication
- **End-to-End Tests**: 30 seconds for AI search (configurable)

## 🐛 Debugging Tests

### Verbose Logging

```bash
python tests/run_all_tests.py --verbose
```

### Individual Test Debugging

```bash
# Run specific test with Python debugger
python -m pdb tests/unit/test_pett_tools.py
```

### Log Analysis

Check the console output for:

- Connection errors
- Authentication failures
- Timeout issues
- Invalid responses

## 📝 Adding New Tests

### Unit Tests

1. Create test file in `tests/unit/`
2. Follow naming convention: `test_<component>.py`
3. Import the component to test
4. Write test functions with descriptive names
5. Add to `run_all_tests.py` if needed

### Integration Tests

1. Create test file in `tests/integration/`
2. Test component interactions
3. Include proper setup and teardown
4. Handle external dependencies gracefully

### End-to-End Tests

1. Create test file in `tests/e2e/`
2. Test complete user workflows
3. Include timeout handling
4. Test error scenarios

## 🚨 Common Issues

### Authentication Failures

- Check `PRIVY_TOKEN` environment variable
- Verify token is valid and not expired
- Check network connectivity

### Timeout Issues

- Increase timeout values for slow connections
- Check server availability
- Verify WebSocket URL is correct

### Import Errors

- Ensure you're running from the project root
- Check Python path includes project directory
- Verify all dependencies are installed

## 📈 Test Coverage

The test suite covers:

- ✅ Component creation and initialization
- ✅ Input validation and error handling
- ✅ WebSocket connection and authentication
- ✅ Pet actions and responses
- ✅ AI search functionality
- ✅ Timeout and error scenarios
- ✅ Message handling and parsing

## 🤝 Contributing

When adding new features:

1. Write corresponding tests
2. Ensure all existing tests pass
3. Add tests to appropriate category
4. Update this README if needed
5. Run the full test suite before submitting

## 📞 Support

For test-related issues:

1. Check the logs for detailed error messages
2. Verify environment setup
3. Run tests individually to isolate issues
4. Check the main project documentation
