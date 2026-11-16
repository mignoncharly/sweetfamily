"""Exact matching support, conditional privacy check and uniform sampling. No persistence."""

import secrets
import time


class InvalidRules(ValueError):
    pass


def budget(deadline):
    if deadline is not None and time.monotonic() > deadline:
        raise TimeoutError("Draw computation budget exceeded")


def graph(member_ids, exclusions):
    ids = tuple(sorted(member_ids))
    if len(set(ids)) != len(ids) or not 4 <= len(ids) <= 20:
        raise InvalidRules("Il faut entre 4 et 20 personnes distinctes.")
    index = {name: i for i, name in enumerate(ids)}
    rows = [set(range(len(ids))) - {i} for i in range(len(ids))]
    for giver, recipient in exclusions:
        if giver not in index or recipient not in index or giver == recipient:
            raise InvalidRules("Exclusion invalide.")
        rows[index[giver]].discard(index[recipient])
    return ids, rows


def support(rows, removed_giver=None, removed_recipient=None):
    """All edges in at least one perfect matching, via alternating-cycle reachability."""
    donors = [i for i in range(len(rows)) if i != removed_giver]
    matched = {}

    def augment(giver, seen):
        for recipient in sorted(rows[giver]):
            if recipient == removed_recipient or recipient in seen:
                continue
            seen.add(recipient)
            if recipient not in matched or augment(matched[recipient], seen):
                matched[recipient] = giver
                return True
        return False

    if not all(augment(g, set()) for g in donors):
        return None
    # On donor vertices: g -> owner(r). An unmatched edge is usable iff on a cycle.
    reach = {g: {g} | {matched[r] for r in rows[g] if r in matched} for g in donors}
    for middle in donors:
        for giver in donors:
            if middle in reach[giver]:
                reach[giver] |= reach[middle]
    return {g: {r for r in rows[g] if r in matched and g in reach[matched[r]]} for g in donors}


def validate_privacy(rows, deadline=None):
    possible = support(rows)
    if possible is None:
        raise InvalidRules("Ces exclusions empêchent un tirage complet.")
    for giver, recipients in possible.items():
        for recipient in recipients:
            budget(deadline)
            remaining = support(rows, giver, recipient)
            if remaining is None or any(len(choices) < 2 for choices in remaining.values()):
                raise InvalidRules(
                    "Ces règles permettraient de déduire l'attribution d'une autre personne."
                )
    return possible


def counts(rows, deadline=None):
    n = len(rows)
    full = (1 << n) - 1
    masks = [sum(1 << r for r in row) for row in rows]
    result = [0] * (full + 1)
    result[full] = 1
    for mask in range(full - 1, -1, -1):
        if not mask % 4096:
            budget(deadline)
        options = masks[mask.bit_count()] & (full ^ mask)
        total = 0
        while options:
            bit = options & -options
            options -= bit
            total += result[mask | bit]
        result[mask] = total
    return masks, result


def sample(member_ids, exclusions, timeout=60):
    deadline = time.monotonic() + timeout
    ids, rows = graph(member_ids, exclusions)
    validate_privacy(rows, deadline)
    masks, table = counts(rows, deadline)
    if table[0] == 0:
        raise InvalidRules("Aucun tirage complet.")
    result = []
    used = 0
    full = (1 << len(ids)) - 1
    for giver in range(len(ids)):
        budget(deadline)
        ticket = secrets.randbelow(table[used])
        options = masks[giver] & (full ^ used)
        while options:
            bit = options & -options
            options -= bit
            weight = table[used | bit]
            if ticket < weight:
                result.append((ids[giver], ids[bit.bit_length() - 1]))
                used |= bit
                break
            ticket -= weight
        else:
            raise RuntimeError("Invalid weighted sampling state")
    return result


def validate_result(member_ids, exclusions, result):
    ids, rows = graph(member_ids, exclusions)
    allowed = {giver: {ids[r] for r in rows[i]} for i, giver in enumerate(ids)}
    if (
        len(result) != len(ids)
        or {g for g, _ in result} != set(ids)
        or {r for _, r in result} != set(ids)
    ):
        raise InvalidRules("Résultat non bijectif.")
    if any(r not in allowed[g] for g, r in result):
        raise InvalidRules("Attribution non autorisée.")
