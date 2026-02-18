"""Configuration validation utilities."""


def validate_config(config: dict) -> list[str]:
    """Validate configuration structure.

    Returns a list of error messages. Empty list means valid.
    """
    errors = []

    # Check required sections
    if "edge" not in config:
        errors.append("Missing 'edge' section")
    elif not isinstance(config["edge"], dict):
        errors.append("'edge' must be an object")

    if "central" not in config:
        errors.append("Missing 'central' section")
    elif not isinstance(config["central"], dict):
        errors.append("'central' must be an object")

    # Validate edge config
    edge = config.get("edge", {})
    if "fps" in edge:
        fps = edge["fps"]
        if not isinstance(fps, (int, float)) or fps <= 0 or fps > 120:
            errors.append("edge.fps must be between 1 and 120")

    if "confidence_threshold" in edge:
        conf = edge["confidence_threshold"]
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            errors.append("edge.confidence_threshold must be between 0 and 1")

    if "nms_threshold" in edge:
        nms = edge["nms_threshold"]
        if not isinstance(nms, (int, float)) or nms < 0 or nms > 1:
            errors.append("edge.nms_threshold must be between 0 and 1")

    # Validate central config
    central = config.get("central", {})
    if "port" in central:
        port = central["port"]
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append("central.port must be between 1 and 65535")

    if "inference_mode" in central:
        mode = central["inference_mode"]
        if mode not in ("llm", "vlm"):
            errors.append("central.inference_mode must be 'llm' or 'vlm'")

    # Validate storage config
    storage = config.get("storage", {})
    if "retention_days" in storage:
        days = storage["retention_days"]
        if not isinstance(days, (int, float)) or days < 1:
            errors.append("storage.retention_days must be at least 1")

    # Validate TLS config
    tls = config.get("tls", {})
    if tls.get("enabled"):
        required_certs = ["ca_cert", "server_cert", "server_key"]
        for cert in required_certs:
            if not tls.get(cert):
                errors.append(f"tls.{cert} is required when TLS is enabled")

    # Validate circuit breaker config
    cb = config.get("circuit_breaker", {})
    if "failure_threshold" in cb:
        threshold = cb["failure_threshold"]
        if not isinstance(threshold, int) or threshold < 1:
            errors.append("circuit_breaker.failure_threshold must be at least 1")

    if "recovery_timeout" in cb:
        timeout = cb["recovery_timeout"]
        if not isinstance(timeout, (int, float)) or timeout < 1:
            errors.append("circuit_breaker.recovery_timeout must be at least 1")

    # Validate A/B test config
    ab = config.get("ab_test", {})
    if "traffic_split" in ab:
        split = ab["traffic_split"]
        if not isinstance(split, (int, float)) or split < 0 or split > 1:
            errors.append("ab_test.traffic_split must be between 0 and 1")

    # Validate anomaly config
    anomaly = config.get("anomaly", {})
    if "z_score_threshold" in anomaly:
        z = anomaly["z_score_threshold"]
        if not isinstance(z, (int, float)) or z < 1:
            errors.append("anomaly.z_score_threshold must be at least 1")

    return errors
