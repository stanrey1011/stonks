# Updated calculate_pattern_score to reflect interval-based processing
def calculate_pattern_score(ticker, intervals, lookback=60, window=5):
    score = 0
    pattern_log = []
    seen_counts = defaultdict(int)

    # Use intervals to detect patterns across all timeframes
    for find_func in [
        find_head_shoulders_patterns,
        find_double_patterns,
        find_triangle_patterns,
        find_wedge_patterns
    ]:
        try:
            patterns = find_func(ticker, intervals, window, lookback)
        except Exception as e:
            logging.info(f"[!] Error processing {ticker} in {find_func.__name__}: {e}")
            continue

        for start, end, pattern_type, confidence in patterns:
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                logging.info(f"[!] Invalid confidence '{confidence}' for {pattern_type} → skipping")
                continue

            if confidence < 0.2:
                continue

            if seen_counts[pattern_type] >= MAX_PER_PATTERN:
                continue
            seen_counts[pattern_type] += 1

            weight = PATTERN_SCORES.get(pattern_type, 0)
            contribution = round(confidence * weight)
            logger.debug(f"{pattern_type} → confidence={confidence}, weight={weight}, contribution={contribution}")
            score += contribution
            pattern_log.append((start.date(), end.date(), pattern_type, confidence, contribution))

    return score, pattern_log
