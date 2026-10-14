"""Opt-in source-bound batch preparation and independently reviewed append.

Run ``python -m scripts.news_batch_consumer --help`` for the packet interface.
This entry point grants no scheduled admission, broker, or portfolio authority.
"""
from backend.services.news_batch_consumer import main


if __name__ == "__main__":
    main()
