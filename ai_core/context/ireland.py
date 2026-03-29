def get_ireland_market_context() -> dict:
    return {
        "country": "Ireland",
        "currency": "EUR",

        # Mileage logic (relative, not fixed)
        "avg_mileage_per_year": 15000,

        # Fuel adjustment
        "diesel_mileage_factor": 1.2,
        "petrol_mileage_factor": 1.0,

        # Market behaviour
        "negotiation": {
            "low": 0.05,
            "medium": 0.10,
            "high": 0.20
        },

        "market_liquidity": "medium",

        # Reliability segmentation
        "high_reliability_brands": [
            "Toyota", "Honda", "Mazda", "Hyundai", "Kia"
        ],
        "medium_reliability_brands": [
            "Volkswagen", "Ford", "Skoda", "Renault", "Peugeot"
        ],
        "higher_risk_brands": [
            "BMW", "Audi", "Mercedes", "Land Rover", "Jaguar"
        ],

        # Low liquidity (hard to sell)
        "low_liquidity_brands": [
            "Alfa Romeo", "Chrysler", "Lancia"
        ],

        # Ireland-specific issues
        "common_issues": [
            "rust (wet climate)",
            "suspension wear",
            "NCT-related problems"
        ]
    }
