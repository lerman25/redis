#!/usr/bin/env python3
"""
Simple script to insert vectors into Redis vector sets.
This script demonstrates basic vector insertion without complex test infrastructure.
"""

import redis
import struct
import random
import sys
import time


def generate_random_vector(dim):
    """Generate a random vector of specified dimension"""
    return [random.uniform(-1.0, 1.0) for _ in range(dim)]


def connect_to_redis(port=6379):
    """Connect to Redis instance"""
    try:
        r = redis.Redis(host='localhost', port=port, decode_responses=False)
        r.ping()
        print(f"✅ Connected to Redis on port {port}")
        return r
    except redis.ConnectionError:
        print(f"❌ Failed to connect to Redis on port {port}")
        print("Make sure Redis is running with the vector-sets module loaded")
        sys.exit(1)


def insert_vectors_fp32(redis_client, key, vectors, item_prefix="item"):
    """Insert vectors using FP32 format"""
    print(f"\n📝 Inserting {len(vectors)} vectors using FP32 format...")
    
    for i, vec in enumerate(vectors):
        # Pack vector as FP32 bytes
        vec_bytes = struct.pack(f'{len(vec)}f', *vec)
        item_name = f"{item_prefix}:{i}"
        
        try:
            result = redis_client.execute_command('VADD', key, 'FP32', vec_bytes, item_name)
            if result == 1:
                print(f"  ✅ Added {item_name} (dim={len(vec)})")
            else:
                print(f"  ⚠️  {item_name} already exists")
        except Exception as e:
            print(f"  ❌ Failed to add {item_name}: {e}")


def insert_vectors_values(redis_client, key, vectors, item_prefix="item"):
    """Insert vectors using VALUES format"""
    print(f"\n📝 Inserting {len(vectors)} vectors using VALUES format...")
    
    for i, vec in enumerate(vectors):
        item_name = f"{item_prefix}:{i}"
        
        # Build command: VADD key VALUES dim val1 val2 ... item_name
        args = ['VADD', key, 'VALUES', len(vec)] + [str(x) for x in vec] + [item_name]
        
        try:
            result = redis_client.execute_command(*args)
            if result == 1:
                print(f"  ✅ Added {item_name} (dim={len(vec)})")
            else:
                print(f"  ⚠️  {item_name} already exists")
        except Exception as e:
            print(f"  ❌ Failed to add {item_name}: {e}")


def insert_vectors_with_cas(redis_client, key, vectors, item_prefix="item"):
    """Insert vectors using CAS (Check-And-Set) option"""
    print(f"\n📝 Inserting {len(vectors)} vectors with CAS option...")
    
    for i, vec in enumerate(vectors):
        vec_bytes = struct.pack(f'{len(vec)}f', *vec)
        item_name = f"{item_prefix}:{i}"
        
        try:
            result = redis_client.execute_command('VADD', key, 'FP32', vec_bytes, item_name, 'CAS')
            if result == 1:
                print(f"  ✅ Added {item_name} with CAS (dim={len(vec)})")
            else:
                print(f"  ⚠️  {item_name} already exists (CAS)")
        except Exception as e:
            print(f"  ❌ Failed to add {item_name} with CAS: {e}")


def check_vector_set_info(redis_client, key):
    """Check information about the vector set"""
    try:
        # Get cardinality
        card = redis_client.execute_command('VCARD', key)
        print(f"📊 Vector set '{key}' contains {card} vectors")
        
        # Get dimension
        dim = redis_client.execute_command('VDIM', key)
        print(f"📏 Vector dimension: {dim}")
        
        return card, dim
    except Exception as e:
        print(f"❌ Failed to get vector set info: {e}")
        return 0, 0


def main():
    """Main function"""
    print("🚀 Redis Vector Insertion Script")
    print("=" * 50)
    
    # Configuration
    REDIS_PORT = 6379
    VECTOR_SET_KEY = "test:vectors"
    VECTOR_DIM = 128
    NUM_VECTORS = 10
    
    # Connect to Redis
    redis_client = connect_to_redis(REDIS_PORT)
    
    # Check current thread configuration
    try:
        config_result = redis_client.execute_command('CONFIG', 'GET', 'vectorset-hnsw-max-threads')
        if len(config_result) >= 2:
            threads = config_result[1]
            print(f"🔧 Current vectorset-hnsw-max-threads: {threads}")
        else:
            print("⚠️  Could not read vectorset-hnsw-max-threads config")
    except Exception as e:
        print(f"⚠️  Error reading config: {e}")
    
    # Clear existing data
    print(f"\n🧹 Clearing existing data for key '{VECTOR_SET_KEY}'")
    redis_client.delete(VECTOR_SET_KEY)
    
    # Generate test vectors
    print(f"\n🎲 Generating {NUM_VECTORS} random {VECTOR_DIM}D vectors...")
    vectors = [generate_random_vector(VECTOR_DIM) for _ in range(NUM_VECTORS)]
    
    # Method 1: Insert using FP32 format
    insert_vectors_fp32(redis_client, VECTOR_SET_KEY, vectors[:3], "fp32_item")
    check_vector_set_info(redis_client, VECTOR_SET_KEY)
    
    # Method 2: Insert using VALUES format
    insert_vectors_values(redis_client, VECTOR_SET_KEY, vectors[3:6], "values_item")
    check_vector_set_info(redis_client, VECTOR_SET_KEY)
    
    # Method 3: Insert using CAS option
    insert_vectors_with_cas(redis_client, VECTOR_SET_KEY, vectors[6:9], "cas_item")
    check_vector_set_info(redis_client, VECTOR_SET_KEY)
    
    # Try to insert duplicate with CAS (should return 0)
    print(f"\n🔄 Testing duplicate insertion with CAS...")
    duplicate_vec = vectors[0]
    vec_bytes = struct.pack(f'{len(duplicate_vec)}f', *duplicate_vec)
    try:
        result = redis_client.execute_command('VADD', VECTOR_SET_KEY, 'FP32', vec_bytes, 'fp32_item:0', 'CAS')
        print(f"  Duplicate insertion result: {result} (should be 0)")
    except Exception as e:
        print(f"  ❌ Error with duplicate CAS: {e}")
    
    # Final status
    print(f"\n📈 Final Status:")
    final_card, final_dim = check_vector_set_info(redis_client, VECTOR_SET_KEY)
    
    print(f"\n✅ Vector insertion completed!")
    print(f"   Total vectors inserted: {final_card}")
    print(f"   Vector dimension: {final_dim}")
    print(f"   Redis key: {VECTOR_SET_KEY}")


if __name__ == "__main__":
    main()
