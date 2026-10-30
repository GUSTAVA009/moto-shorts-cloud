"""Plan safe next original Deep render from independently approved audio."""


def pending_verified_previews(catalog, reserved_ids):
    """Never mistake a script for a synthesised and approved new MP4."""
    from deep_voice import ready
    reserved = set(reserved_ids)
    return [ep["id"] for ep in catalog["episodes"]
            if ep.get("auto_preview") is True
            and ep.get("auto_publish") is False
            and ep.get("editorial_rejected") is not True
            and ep.get("visual_review_failed") is not True
            and ep["id"] not in reserved
            and ready(ep)]
