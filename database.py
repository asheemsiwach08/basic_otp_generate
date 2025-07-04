import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from supabase import create_client, Client
from config import settings

class SupabaseOTPStorage:
    def __init__(self):
        # Check if environment variables are set and not empty
        if not settings.SUPABASE_URL or settings.SUPABASE_URL.strip() == "":
            raise ValueError("SUPABASE_URL environment variable is required")
        
        if not settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_SERVICE_ROLE_KEY.strip() == "":
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY environment variable is required")

        try:
            self.supabase: Client = create_client(
                settings.SUPABASE_URL, 
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
            print("Supabase client initialized successfully")
        except Exception as e:
            print(f"Error initializing Supabase client: {e}")
            raise
        self.table_name = "otp_storage"
        # self._ensure_table_exists()
    
    # def _ensure_table_exists(self):
    #     """Ensure the OTP storage table exists"""
    #     try:
    #         # Check if table exists by trying to select from it
    #         self.supabase.table(self.table_name).select("id").limit(1).execute()
    #         print(f"Table {self.table_name} exists and is accessible")
    #     except Exception as e:
    #         print(f"Error accessing table {self.table_name}: {e}")
    #         print("This might be due to:")
    #         print("1. Table doesn't exist - run the SQL setup script")
    #         print("2. Permission issues - check service role permissions")
    #         print("3. RLS policies blocking access")
    #         # Table doesn't exist, create it
    #         self._create_table()
    
    # def _create_table(self):
    #     """Create the OTP storage table"""
    #     # Note: In Supabase, you typically create tables via SQL editor or migrations
    #     # This is a fallback method
    #     create_table_sql = f"""
    #     CREATE TABLE IF NOT EXISTS {self.table_name} (
    #         id SERIAL PRIMARY KEY,
    #         phone_number VARCHAR(20) NOT NULL,
    #         otp VARCHAR(10) NOT NULL,
    #         created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    #         expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    #         is_used BOOLEAN DEFAULT FALSE
    #     );
        
    #     CREATE INDEX IF NOT EXISTS idx_otp_phone_number ON {self.table_name}(phone_number);
    #     CREATE INDEX IF NOT EXISTS idx_otp_expires_at ON {self.table_name}(expires_at);
    #     """
        
    #     try:
    #         self.supabase.rpc('exec_sql', {'sql': create_table_sql}).execute()
    #     except Exception as e:
    #         print(f"Warning: Could not create table automatically: {e}")
    #         print("Please create the table manually in Supabase SQL editor:")
    #         print(create_table_sql)
    
    def set_otp(self, phone_number: str, otp: str, expiry_seconds: int):
        """Store OTP with expiry time"""
        # Use timezone-aware datetime
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)
        
        # Delete any existing OTP for this phone number
        self.supabase.table(self.table_name).delete().eq("phone_number", phone_number).execute()
        
        # Insert new OTP
        data = {
            "phone_number": phone_number,
            "otp": otp,
            "expires_at": expires_at.isoformat(),
            "is_used": False
        }
        
        self.supabase.table(self.table_name).insert(data).execute()
    
    def get_otp(self, phone_number: str) -> Optional[str]:
        """Get OTP for phone number if not expired"""
        try:
            response = self.supabase.table(self.table_name).select(
                "otp, expires_at, is_used"
            ).eq("phone_number", phone_number).eq("is_used", False).execute()
            
            if not response.data:
                return None
            
            otp_record = response.data[0]
            
            # Parse the expires_at string to timezone-aware datetime
            if isinstance(otp_record["expires_at"], str):
                # Handle ISO format string
                expires_at = datetime.fromisoformat(otp_record["expires_at"].replace("Z", "+00:00"))
            else:
                # Handle datetime object
                expires_at = otp_record["expires_at"]
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            # Compare with current UTC time
            current_time = datetime.now(timezone.utc)
            
            # Check if OTP has expired
            if current_time > expires_at:
                # Mark as expired
                self.supabase.table(self.table_name).update(
                    {"is_used": True}
                ).eq("phone_number", phone_number).execute()
                return None
            
            return otp_record["otp"]
            
        except Exception as e:
            print(f"Error getting OTP: {e}")
            return None
    
    def mark_otp_as_used(self, phone_number: str):
        """Mark OTP as used after successful verification"""
        try:
            self.supabase.table(self.table_name).update(
                {"is_used": True}
            ).eq("phone_number", phone_number).execute()
        except Exception as e:
            print(f"Error marking OTP as used: {e}")
    
    def delete_otp(self, phone_number: str):
        """Delete OTP after successful verification (deprecated - use mark_otp_as_used instead)"""
        # For backward compatibility, mark as used instead of deleting
        self.mark_otp_as_used(phone_number)
    
    def is_otp_exists(self, phone_number: str) -> bool:
        """Check if OTP exists and is not expired for phone number"""
        try:
            response = self.supabase.table(self.table_name).select(
                "expires_at, is_used"
            ).eq("phone_number", phone_number).eq("is_used", False).execute()
            
            if not response.data:
                return False
            
            otp_record = response.data[0]
            
            # Parse the expires_at string to timezone-aware datetime
            if isinstance(otp_record["expires_at"], str):
                # Handle ISO format string
                expires_at = datetime.fromisoformat(otp_record["expires_at"].replace("Z", "+00:00"))
            else:
                # Handle datetime object
                expires_at = otp_record["expires_at"]
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            # Compare with current UTC time
            current_time = datetime.now(timezone.utc)
            
            # Check if OTP has expired
            if current_time > expires_at:
                # Mark as expired
                self.supabase.table(self.table_name).update(
                    {"is_used": True}
                ).eq("phone_number", phone_number).execute()
                return False
            
            return True
            
        except Exception as e:
            print(f"Error checking OTP existence: {e}")
            return False
    
    def cleanup_expired(self):
        """Clean up expired OTPs"""
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            self.supabase.table(self.table_name).update(
                {"is_used": True}
            ).lt("expires_at", current_time).execute()
        except Exception as e:
            print(f"Error cleaning up expired OTPs: {e}")

# Global instance
try:
    print("Attempting to initialize Supabase storage...")
    otp_storage = SupabaseOTPStorage()
    print("Supabase storage initialized successfully")
except Exception as e:
    print(f"Warning: Could not initialize Supabase storage: {e}")
    print("Error type:", type(e).__name__)
    print("Falling back to local storage...")
    
    # Fallback to local storage
    import time
    from threading import Lock
    from typing import Dict, Tuple, Optional
    
    class LocalOTPStorage:
        def __init__(self):
            self._storage: Dict[str, Tuple[str, float]] = {}
            self._used_otps: Dict[str, Tuple[str, float]] = {}  # Track used OTPs
            self._lock = Lock()
        
        def set_otp(self, phone_number: str, otp: str, expiry_seconds: int):
            with self._lock:
                expiry_time = time.time() + expiry_seconds
                self._storage[phone_number] = (otp, expiry_time)
        
        def get_otp(self, phone_number: str) -> Optional[str]:
            with self._lock:
                if phone_number not in self._storage:
                    return None
                
                otp, expiry_time = self._storage[phone_number]
                
                if time.time() > expiry_time:
                    del self._storage[phone_number]
                    return None
                
                return otp
        
        def mark_otp_as_used(self, phone_number: str):
            """Mark OTP as used after successful verification"""
            with self._lock:
                if phone_number in self._storage:
                    otp, expiry_time = self._storage[phone_number]
                    self._used_otps[phone_number] = (otp, expiry_time)
                    del self._storage[phone_number]
        
        def delete_otp(self, phone_number: str):
            """Delete OTP after successful verification (deprecated - use mark_otp_as_used instead)"""
            # For backward compatibility, mark as used instead of deleting
            self.mark_otp_as_used(phone_number)
        
        def is_otp_exists(self, phone_number: str) -> bool:
            with self._lock:
                if phone_number not in self._storage:
                    return False
                
                otp, expiry_time = self._storage[phone_number]
                
                if time.time() > expiry_time:
                    del self._storage[phone_number]
                    return False
                
                return True
        
        def cleanup_expired(self):
            with self._lock:
                current_time = time.time()
                expired_keys = [
                    key for key, (otp, expiry_time) in self._storage.items()
                    if current_time > expiry_time
                ]
                for key in expired_keys:
                    del self._storage[key]
    
    otp_storage = LocalOTPStorage() 