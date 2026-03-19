"""GitHub-style alert detection and preprocessing."""

# Alert type -> (border_color, background_color, label_text, text_color)
ALERT_STYLES = {
    "NOTE": ("4493F8", "DBEAFE", "Note", "4493F8"),
    "TIP": ("3FB950", "DCFCE7", "Tip", "3FB950"),
    "IMPORTANT": ("AB7DF8", "F3E8FF", "Important", "AB7DF8"),
    "WARNING": ("D29922", "FEF9C3", "Warning", "D29922"),
    "CAUTION": ("F85149", "FEE2E2", "Caution", "F85149"),
}


def detect_alert_type(token):
    """Check if a block_quote token is a GitHub-style alert.

    Returns the alert type string (e.g. "NOTE") or None.
    Mistune splits [!NOTE] into two text nodes: "[" and "!NOTE]".
    """
    children = token.get("children", [])
    if not children:
        return None

    first_child = children[0]
    if first_child.get("type") != "paragraph":
        return None

    inlines = first_child.get("children", [])
    if len(inlines) < 2:
        return None

    first_inline = inlines[0]
    second_inline = inlines[1]

    if first_inline.get("type") != "text" or second_inline.get("type") != "text":
        return None

    first_raw = first_inline.get("raw", "") or first_inline.get("text", "")
    second_raw = second_inline.get("raw", "") or second_inline.get("text", "")

    if first_raw != "[":
        return None

    if second_raw.startswith("!") and second_raw.endswith("]"):
        alert_type = second_raw[1:-1].upper()
        if alert_type in ALERT_STYLES:
            return alert_type

    return None


def preprocess_alerts(tokens):
    """Scan AST for GitHub-style alerts in blockquotes and replace with alert tokens."""
    result = []

    for token in tokens:
        if token["type"] == "block_quote":
            alert_type = detect_alert_type(token)
            if alert_type:
                children = token.get("children", [])

                # Strip the [!TYPE] marker from the first paragraph's inlines
                if children and children[0].get("type") == "paragraph":
                    first_para = children[0]
                    inlines = first_para.get("children", [])

                    # Remove the "[" and "!TYPE]" text nodes (first two inlines)
                    stripped = inlines[2:]

                    # Remove leading softbreak if present
                    if stripped and stripped[0].get("type") == "softbreak":
                        stripped = stripped[1:]

                    if stripped:
                        # Keep the first paragraph with remaining inlines
                        body_children = [
                            {"type": "paragraph", "children": stripped}
                        ] + [c for c in children[1:] if c.get("type") != "blank_line"]
                    else:
                        # First paragraph had only the marker; use remaining children
                        body_children = [
                            c for c in children[1:] if c.get("type") != "blank_line"
                        ]
                else:
                    body_children = children

                result.append(
                    {
                        "type": "alert",
                        "attrs": {"alert_type": alert_type},
                        "children": body_children,
                    }
                )
                continue

        result.append(token)

    return result
