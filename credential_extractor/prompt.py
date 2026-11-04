"""Prompts sent to the model.

Phase 3: the original prompt from the base script, unchanged, so the eval
measures only the effect of the new pipeline. Phase 4 replaces it.
"""

SYSTEM = "You extract structured data from documents and answer only with JSON."

USER = """Extract the following information from this medical license document
and return it as JSON:

- is_credential
- holder_name
- credential_type
- license_number
- issuing_authority
- issue_date
- expiration_date
- expiration_status (expired, expiring_soon, valid or no_expiration)
"""
