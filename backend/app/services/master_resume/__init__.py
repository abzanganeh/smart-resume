"""Master-resume service layer (SYSTEM_DESIGN_PHASE_2 §18.4).

Submodules:

- ``chunking``  — split parsed sections into chunks per the §18.4 table.
- ``embedding`` — call OpenAI ``text-embedding-3-small`` with the
  platform-owned key (config setting ``OPENAI_EMBEDDING_KEY``).
- ``crud``      — DB primitives used by the ``/api/profile/resume``
  router and the retrieval service.
"""
