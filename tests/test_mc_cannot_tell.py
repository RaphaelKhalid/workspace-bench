"""Plan 0032 §2.4 (Camila: "all mc for judges should have a 'cannot tell' option") and §2.7.2
(every judge prompt renders the shared token note from its own spec)."""

import pytest

from wsbench import digest, mc, registry
from wsbench.banks import load_bank as j_load
from wsbench.baselines import lucky_guessing
from wsbench.evals.introspection import judge as ij
from wsbench.evals.introspection import prompts as ip

# MC families whose builder appends the escape through mc.options_with_cannot (plan 0032 §2.4.1)
# and the family PRs that convert the rest (introspection's 7th option is infra's, §2.4.2)
PENDING_FAMILY_PR = {}


def _last_option(family: str) -> str:
    """The final option of one real judge option list of ``family``, from its own builder."""
    from wsbench.mcjudge import load_bank

    if family == "chain_intermediates":
        from wsbench.evals.chain_intermediates import judge as j

        _h, items = j.load_bank(registry.bank_path(family))
        return j.shown_options(j.mc_options(items[0])[0])[-1]
    if family == "association":
        from wsbench.evals.association import judge as j

        return j.build_options(j.load_items()[0])[0][-1]
    if family == "conjunctive_association":
        from wsbench.evals.conjunctive_association import judge as j

        return j.build_options(load_bank(family)[0])[0][-1]
    if family == "role_bound_association":
        from wsbench.evals.role_bound_association import judge as j

        bank = load_bank(family)
        block, _golds = j.build_block(bank[0], bank)
        return [ln for ln in block.splitlines() if ln.strip()][-1]
    if family == "relational_multihop":
        from wsbench.evals.relational_multihop import judge as j

        it = load_bank(family)[0]
        return j.build_options(it["id"], it["hop1"], it["hop2"]).shown[-1]
    if family == "moral_rationale":
        from wsbench.evals.moral_rationale import judge as j

        bank = load_bank(family)
        mcs = j.build_mcs(bank[0], *j.build_pools(bank))
        return next(iter(mcs.values())).shown[-1]
    if family == "user_modeling":
        from wsbench.evals.user_modeling import judge as j
        from wsbench.evals.user_modeling import prompts as p

        bank = load_bank(family)["items"]
        opts, _gold = j.build_options(bank)[str(bank[0]["name"])]
        return p.option_lines(opts).splitlines()[-1]
    if family == "directed_modulation":
        from wsbench.evals.directed_modulation import judge as j
        from wsbench.evals.directed_modulation import prompts as p

        _h, items = j.load_bank(registry.bank_path(family))
        opts = j.option_sets(items)[items[0]["id"]][0]
        return p.option_lines(opts).splitlines()[-1]
    if family == "poetry":
        from wsbench.banks import load_bank as load_bank_file
        from wsbench.evals.poetry.options import option_set

        _h, items = load_bank_file(registry.bank_path(family))
        return option_set(items[0])[0][-1]
    if family == "multi_concept_directed_modulation":
        from wsbench.evals.multi_concept_directed_modulation import options as o
        from wsbench.evals.multi_concept_directed_modulation import prompts as p

        _h, items = j_load(registry.bank_path(family))
        opts, _gold = o.option_sets(items)[items[0]["id"]]
        return p.option_lines(opts).splitlines()[-1]
    if family == "knowledge_cutoff":
        from wsbench.evals.knowledge_cutoff import judge as j
        from wsbench.evals.knowledge_cutoff import prompts as p

        it = j.load_items()[0]
        return p.menu(it["options"], it["option_units"]).splitlines()[-1]
    if family == "basic_readout":  # plan 0053: the blind MC bank judge
        from wsbench.banks import load_bank as load_bank_file
        from wsbench.basic.mcjudge_basic import CANNOT_OF, options_for
        from wsbench.basic.prompts import prompt_version_of

        _h, items = load_bank_file(registry.bank_path(family))
        pv = prompt_version_of(family)
        return options_for(items[0], pv=pv, cannot=CANNOT_OF[family]).shown[-1]
    if family == "multihop":
        from wsbench.banks import load_bank as load_bank_file
        from wsbench.basic.mcjudge_bank import options_of

        _h, items = load_bank_file(registry.bank_path(family))
        return options_of(family, items[0])[0][-1]
    if family == "wrong_bridge":
        from wsbench.evals.wrong_bridge import judge as j

        return j.shown_options(j.load_items()[0])[-1]
    if family == "introspection":  # round 4: floored for its diagnostic judge column
        bank = ij.load()
        (u,) = ij.units(bank, bank["items"][:1])
        return u["labels"][-1]
    # the multi-token families: the shared option builder
    from wsbench.banks import load_bank as load_bank_file
    from wsbench.multitoken.options import option_sets

    _h, items = load_bank_file(registry.bank_path(family))
    roles = option_sets(items)[items[0]["id"]]
    return next(iter(roles.values()))[0][-1]


MC_FAMILIES = sorted(set(lucky_guessing.BUILDERS) - set(PENDING_FAMILY_PR))


@pytest.mark.parametrize("family", MC_FAMILIES)
def test_every_mc_judge_ends_with_cannot(family):
    registry.load_all()
    last = _last_option(family)
    assert mc.is_cannot(last.split(". ", 1)[-1].strip()), (family, last)


def test_introspection_cannot_is_the_seventh_option():
    bank = ij.load()
    scope = [it for it in bank["items"] if it["kind"] == "inject"][:1]
    (u,) = [u for u in ij.units(bank, scope) if u["id"] == scope[0]["id"]]
    assert u["labels"][-1] == mc.CANNOT and u["labels"][-2] != mc.CANNOT
    assert ij.NONE_OPTION in u["labels"] and len(u["labels"]) == 7
    assert 'Choose "cannot tell from the readout" when the samples neither name' in ip.SYSTEM


def test_cannot_pick_is_never_a_pass():
    labels = ["a", "b", ij.NONE_OPTION, mc.CANNOT]
    assert ij.resolve({"choice": 4, "quote": ""}, labels, ["a"], "text") == (ij.NONE_OPTION, False)
    assert mc.classify(4, 1, 4) == "cannot_tell"


@pytest.mark.parametrize("family", sorted(set(registry.FAMILIES) or ["association"]))
def test_token_note_rendered_from_spec(family):
    """Any digest-side token note a family's judge receives is mc.token_note of its own spec."""
    registry.load_all()
    spec = registry.FAMILIES.get(family)
    if spec is None:
        pytest.skip("not registered")
    want = mc.token_note(
        spec.flat_types, multi_select=spec.multi_select, targets=spec.targets_judge
    )
    assert digest.token_note_of(family) == want
