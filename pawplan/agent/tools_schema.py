TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Search curated PawPlan knowledge documents about pet care, "
                "Hong Kong city rules, and permitted-restaurant policies. "
                "Use this for how/why/can-I questions that need sourced answers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language knowledge query",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["query", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_parks",
            "description": (
                "Search LCSD pet gardens (dedicated dog/pet parks) and "
                "Inclusive Parks for Pets by district."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "Hong Kong district, e.g. Sha Tin, Wan Chai",
                    },
                    "park_type": {
                        "type": "string",
                        "description": "Optional: pet_garden or inclusive_park",
                    },
                    "require_dog_latrine": {
                        "type": "boolean",
                        "description": "If true, only return parks marked with dog latrine",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["district", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_restaurants",
            "description": (
                "Search dog-permitted restaurants in the PawPlan database. "
                "Use only for dining place recommendation requests with a district."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "Hong Kong district, e.g. Sha Tin, Mong Kok",
                    },
                    "cuisine": {
                        "type": "string",
                        "description": "Optional cuisine code, e.g. dim_sum, cafe",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["district", "limit"],
                "additionalProperties": False,
            },
        },
    },
]
