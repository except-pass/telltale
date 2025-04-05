# Testing Strategy

## Live Database Instance

This test suite uses a live Neo4j database instance for testing. This approach was chosen because a significant portion of the application logic resides in Cypher queries, making it important to test against a real database engine.

## Database Management

Currently, this is a proof of concept implementation, so we take a pragmatic approach to database management during testing:

- Tests create and manipulate their own test data
- The database is cleared between test runs but not between individual tests
- Each test is responsible for setting up its required test data

## Test Utilities

The `test_utils.py` file provides common utilities for testing, including:

- `Neo4jTestCase`: A base class for tests that need database access
- Helper methods for setting up and tearing down test data
- Connection management to the test database

## Running Tests

Make sure you have a Neo4j instance running (the Docker Compose configuration includes this). Tests will connect to the database specified in your environment configuration.

## Future Improvements

As the project matures, we plan to:

- Implement more structured database cleanup between tests
- Add fixtures for common test data
- Potentially introduce test database isolation 