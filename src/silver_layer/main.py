"""Lambda handler entry point for Silver layer."""

import logging
from .orchestrator import run_pipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """AWS Lambda handler for Silver layer transformation.

    Args:
        event: Lambda event (unused, keeping for Lambda interface)
        context: Lambda context (unused, keeping for Lambda interface)

    Returns:
        Response dict with status and result
    """
    logger.info("Lambda handler triggered")
    result = run_pipeline()
    logger.info(f"Lambda execution result: {result}")
    return result


if __name__ == "__main__":
    # Local execution for testing
    import os
    os.environ.setdefault("AWS_REGION", "ap-southeast-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-1")

    logger.info("Running Silver layer pipeline locally...")
    result = run_pipeline()
    print(f"\n{'=' * 50}")
    print("Pipeline Result:")
    print(f"{'=' * 50}")
    print(f"Status Code: {result['statusCode']}")
    print(f"Message: {result['message']}")
    if "object_key" in result:
        print(f"Object Key: {result['object_key']}")
    if "error" in result:
        print(f"Error: {result['error']}")
