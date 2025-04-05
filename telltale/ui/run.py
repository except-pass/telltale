#!/usr/bin/env python
"""
Run script for the Telltale Streamlit UI.
"""
import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

def main():
    """Run the Streamlit app."""
    # Get the directory of this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the app.py path
    app_path = os.path.join(current_dir, "app.py")
    
    # Run the Streamlit app
    cmd = ["streamlit", "run", app_path, "--server.port=8501", "--server.address=0.0.0.0"]
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        logger.info("Streamlit app stopped by user")
    except Exception as e:
        logger.error(f"Error running Streamlit app: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 