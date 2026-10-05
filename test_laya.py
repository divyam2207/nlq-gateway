import laya_mlx as laya

def main():
    print("Loading Laya MLX model (aac6fef/laya-mlx)...")
    agent = laya.load("aac6fef/laya-mlx")
    print("Model loaded successfully!")

    prompt = "I was billed twice for my subscription. Please refund the extra charge."
    tasks = {
        "department": {
            "type": "choice",
            "instructions": "Which department should handle this request?",
            "criteria": ["billing", "technical", "sales"]
        },
        "is_refund_requested": {
            "type": "noul",
            "instructions": "Does the user explicitly ask for a refund?"
        }
    }

    print(f"\nInput Text: '{prompt}'")
    print("Running decision inference...")
    result = agent.predict(prompt, tasks)
    print("\nDecision Results:")
    print(result)

if __name__ == "__main__":
    main()
