"""CLI interface for managing nodes and relationships."""

import argparse
import logging
from typing import Optional

from telltale.core.node_manager import NodeManager

logger = logging.getLogger(__name__)

def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration.
    
    Args:
        verbose: Whether to use DEBUG level logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def main(args: Optional[list] = None) -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Natural language interface for managing diagnostic nodes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode (no prompts)"
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.8,
        help="Threshold for considering nodes similar (0.0 to 1.0)"
    )

    args = parser.parse_args(args)
    setup_logging(args.verbose)

    manager = NodeManager(similarity_threshold=args.similarity_threshold)

    print("\nWelcome to the Telltale Node Manager!")
    print("Enter your natural language description of nodes and relationships.")
    print("Enter 'quit' or press Ctrl+D to exit.\n")

    try:
        while True:
            try:
                prompt = input("> ")
                if prompt.lower() in ("quit", "exit"):
                    break

                manager.process_natural_language(
                    prompt,
                    interactive=not args.non_interactive
                )
                print("\nNodes and relationships processed successfully!")

            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                continue
            except EOFError:
                break
            except Exception as e:
                logger.error(f"Error processing input: {e}", exc_info=args.verbose)
                print(f"\nError: {e}")

    except KeyboardInterrupt:
        print("\nGoodbye!")

if __name__ == "__main__":
    main() 