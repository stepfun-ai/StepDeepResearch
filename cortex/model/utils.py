import copy


def merge_delta_message(d1: dict | None, d2: dict | None) -> dict:
    """
    Merge two message dictionaries.

    Args:
        d1: Accumulated message dictionary, can be dict or None
        d2: Delta message dictionary, can be dict or None

    Returns:
        Merged dictionary

    Note:
        role and id fields will retain d1's values (if present), so during streaming
        the role from the first chunk can be correctly preserved.
    """
    if d1 is None:
        return d2
    if d2 is None:
        return d1

    result = copy.deepcopy(d1)  # Create a copy of d1
    for key, value in d2.items():
        if key in result:
            if key == "index":
                pass
            elif key == "role" or key == "id":
                # Retain d1's value for role and id (if present), otherwise use d2's value
                if not result[key] and value:
                    result[key] = value
            elif key == "tool_calls":
                if value and not isinstance(value, list):
                    value = [value]
                toolcall = {}
                if result[key]:
                    for v in result[key]:
                        toolcall[v["index"]] = v
                if value:
                    for v in value:
                        toolcall_id = v["index"]
                        if toolcall_id in toolcall:
                            toolcall[toolcall_id] = merge_delta_message(
                                toolcall[toolcall_id], v
                            )
                        else:
                            toolcall[toolcall_id] = v
                result[key] = []
                for k, v in toolcall.items():
                    result[key].append(v)
            elif isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = merge_delta_message(result[key], value)
            elif isinstance(result[key], str) and isinstance(value, str) and value:
                # type/id are fixed enum-like values, don't concatenate (avoids "functionfunction...")
                if key in ("type", "id"):
                    result[key] = value
                else:
                    result[key] += value
            elif isinstance(result[key], list) and isinstance(value, list):
                result[key] += value
            elif isinstance(result[key], (int, float)) and isinstance(
                    value, (int, float)
            ):
                result[key] += value
            elif value:
                # Type mismatch, override with d2's value
                result[key] = value
        else:
            result[key] = value
    # Merge data like [{'type': 'text', 'text': '...'}], combining consecutive items with the same type into one
    for key, value in result.items():
        if isinstance(value, list):
            new_value = []
            last_type = None
            last_index = None
            for i in range(len(value)):
                if "type" in value[i]:
                    current_type = value[i]["type"]
                    current_index = value[i].get("index", None)
                    if current_type == last_type and current_index == last_index:
                        # Merge all non-type fields
                        for k, v in value[i].items():
                            if k != "type":
                                if k in new_value[-1]:
                                    new_value[-1][k] += v
                                else:
                                    new_value[-1][k] = v
                    else:
                        new_value.append(value[i])
                    last_type = current_type
                    last_index = current_index
            result[key] = new_value

    return result
