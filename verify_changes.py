import os
import sys
from dotenv import load_dotenv

load_dotenv()

def verify_imports():
    print("Verifying imports...")
    try:
        from app.config import LLM_MODEL_NAME
        print(f"Config loaded. LLM_MODEL_NAME: {LLM_MODEL_NAME}")
        
        import app.services.market_data
        print("app.services.market_data imported successfully")
        
        import app.services.sentiment
        print("app.services.sentiment imported successfully")
        
        import app.routers
        print("app.routers imported successfully")

        import app.engine.workflow
        print("app.engine.workflow imported successfully")

        import app.llm.llm_clients
        print("app.llm.llm_clients imported successfully")
        
        # Check restored modules
        import app.routers.basic_analysis
        print("app.routers.basic_analysis imported successfully")

        import app.routers.opinion
        print("app.routers.opinion imported successfully")

        import app.routers.market
        print("app.routers.market imported successfully")

    except ImportError as e:
        print(f"Import failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

    print("All critical modules imported successfully.")

if __name__ == "__main__":
    verify_imports()
