import asyncio
import asyncpg
import os

async def test_passwords():
    passwords = ['', 'postgres', 'password', 'admin', 'root', '123456']
    for pwd in passwords:
        try:
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                database='postgres',
                user='postgres',
                password=pwd
            )
            await conn.close()
            print(f'SUCCESS: Password is "{pwd}"')
            return True
        except Exception as e:
            print(f'FAILED: "{pwd}" - {str(e)[:50]}...')

    print('None of the common passwords worked.')
    return False

if __name__ == "__main__":
    success = asyncio.run(test_passwords())
    if not success:
        print("\nTo reset the password, you can:")
        print("1. Stop PostgreSQL service")
        print("2. Start PostgreSQL in single-user mode")
        print("3. Change the password")
        print("4. Restart PostgreSQL service")
        print("\nWould you like me to help you reset the password?")