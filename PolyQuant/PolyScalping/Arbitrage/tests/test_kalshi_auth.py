
import os
import sys
import unittest
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.kalshi import KalshiCollector

class TestKalshiAuth(unittest.TestCase):
    def setUp(self):
        # Generate a test RSA private key
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Determine path for test key file
        self.key_file = "test_private_key.pem"
        with open(self.key_file, "wb") as f:
            f.write(pem)
            
        # Set environment variables for the test
        os.environ["KALSHI_KEY_ID"] = "test-key-id"
        os.environ["KALSHI_PRIVATE_KEY"] = self.key_file
        
    def tearDown(self):
        # Cleanup
        if os.path.exists(self.key_file):
            os.remove(self.key_file)
        if "KALSHI_KEY_ID" in os.environ:
            del os.environ["KALSHI_KEY_ID"]
        if "KALSHI_PRIVATE_KEY" in os.environ:
            del os.environ["KALSHI_PRIVATE_KEY"]

    def test_signature_generation(self):
        """Test that authentication headers are generated correctly."""
        collector = KalshiCollector()
        
        headers = collector._get_auth_headers("GET", "/trade-api/v2/markets")
        
        self.assertIn("KALSHI-ACCESS-KEY", headers)
        self.assertEqual(headers["KALSHI-ACCESS-KEY"], "test-key-id")
        
        self.assertIn("KALSHI-ACCESS-TIMESTAMP", headers)
        self.assertIn("KALSHI-ACCESS-SIGNATURE", headers)
        
        print(f"\nGenerated Headers:\n{headers}")

if __name__ == "__main__":
    unittest.main()
