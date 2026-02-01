#!/usr/bin/env python3
"""
Debug script to compare phone numbers and see why verification fails.
This helps identify formatting differences between .env and Telegram's format.
"""

from config import Config

def normalize_phone(number: str) -> str:
    """Ensure phone number starts with +."""
    num = str(number).strip()
    if num.isdigit():
        return f"+{num}"
    if not num.startswith('+'):
        return f"+{num}"
    return num

def main():
    print("=" * 60)
    print("Phone Number Debug Tool")
    print("=" * 60)

    # Load config
    try:
        config = Config()
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    print("\nAdmin phone numbers from .env:")
    print("-" * 60)
    for i, phone in enumerate(config.admin_phone_numbers, 1):
        print(f"{i}. '{phone}' (length: {len(phone)})")
        # Show character codes to detect hidden characters
        print(f"   Bytes: {[ord(c) for c in phone]}")

    print("\n" + "=" * 60)
    print("Manual Test:")
    print("=" * 60)

    # Test the specific numbers
    test_numbers = [
        "+989935880577",
        "+98936934430",
        "989935880577",
        "98936934430",
    ]

    print("\nTesting different formats:")
    for test_num in test_numbers:
        normalized = normalize_phone(test_num)
        match = normalized in config.admin_phone_numbers
        print(f"\nOriginal:   '{test_num}'")
        print(f"Normalized: '{normalized}'")
        print(f"Match:      {'✅ YES' if match else '❌ NO'}")
        if match:
            print(f"Index:      {config.admin_phone_numbers.index(normalized)}")

    print("\n" + "=" * 60)
    print("Suggestions:")
    print("=" * 60)
    print("1. Check your .env file for the exact format of ADMIN_PHONE_NUMBERS")
    print("2. When testing, check the bot logs for 'Normalized phone number: ...'")
    print("3. Compare what Telegram sends vs what's in your .env")
    print("4. Telegram might add/remove spaces or use different country code format")
    print("\nCommon issues:")
    print("- Extra spaces in .env: ['+98 993 588 0577'] vs ['+989935880577']")
    print("- Missing country code: ['9935880577'] vs ['+989935880577']")
    print("- Different separators: ['+98-993-588-0577'] vs ['+989935880577']")

if __name__ == "__main__":
    main()
