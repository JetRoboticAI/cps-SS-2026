import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRIVATE_KEY_FILE = "server_private_key.bin"
PUBLIC_KEY_FILE = "server_public_key.bin"

def generate_keys_if_needed():
    if os.path.exists(PRIVATE_KEY_FILE):
        return

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # save private key
    with open(PRIVATE_KEY_FILE, "wb") as f:
        f.write(private_key.private_bytes_raw())

    # save public key
    with open(PUBLIC_KEY_FILE, "wb") as f:
        f.write(public_key.public_bytes_raw())

    print("Keys generated and saved")

if __name__ == "__main__":
    generate_keys_if_needed()