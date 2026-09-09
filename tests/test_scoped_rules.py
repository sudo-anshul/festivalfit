from datetime import date
from copy import deepcopy

import pytest
from app.evidence import validate_assessment
from app.models import Assessment, Film, Source
from app.rules import extract_dates, runtime_rule, rule_kind
from test_evidence import candidate, QUOTES, FILM

TODAY = date(2026,9,9)


def run(data=None, film=FILM, extra_sources=(), title='Example Festival 2027 Shorts'):
    data = data or candidate()
    source = Source(id='S1', title=title, url='https://festival.example/rules', excerpts=[c['quote'] for c in data['checks'] if c.get('quote')] + [r['quote'] for r in data.get('additional_rules',[])])
    return validate_assessment(Assessment.model_validate({'festivals':[data]}), [source,*extra_sources], TODAY, film)[0]


def change(criterion,quote):
    data=candidate()
    next(c for c in data['checks'] if c['criterion']==criterion)['quote']=quote
    return data


def test_explicit_positive_control_keeps_useful_match():
    r=run()
    assert r['status']=='likely_fit'
    assert r['matched']==6
    assert r['scope_status']=='scoped'


@pytest.mark.parametrize('name,category,edition', [('Invented Festival','Shorts','2027'),('Example Festival','Feature competition','2027'),('Example Festival','Shorts','2024')])
def test_wrong_identity_category_and_edition_do_not_pass(name,category,edition):
    r=run(candidate(name=name,category=category,edition=edition))
    assert r['status']=='review_required'
    assert r['scope_issues']
    assert not any(c['status']=='met' for c in r['checks'])


@pytest.mark.parametrize('criterion,quote',[
 ('country','Films produced in India are not eligible for this category.'),
 ('genre','Fiction films are not eligible for this category.'),
 ('completion','Films must be completed after January 1, 2027.'),
])
def test_explicit_exclusions_override_wrong_upstream_match(criterion,quote):
    r=run(change(criterion,quote))
    assert next(c for c in r['checks'] if c['criterion']==criterion)['status']=='not_met'
    assert r['status']=='not_fit'


def test_online_release_conflicts_with_required_world_premiere():
    r=run(change('premiere','Films must retain their world premiere status.'),film=FILM.model_copy(update={'premiere_status':'Publicly available online'}))
    assert r['status']=='not_fit'


def test_future_event_cannot_replace_expired_deadline():
    d=change('deadline','Submission deadline: August 1, 2026. Festival screening: October 1, 2026.')
    r=run(d)
    assert r['deadline'] is None
    assert r['status']!='likely_fit'


def test_conflicting_same_scope_sources_remain_visible():
    other=Source(id='S2',title='Example Festival 2027 Shorts',url='https://festival.example/update',excerpts=['Films produced in India are not eligible.'])
    r=run(extra_sources=[other]); c=next(c for c in r['checks'] if c['criterion']=='country')
    assert c['status']=='unknown'
    assert c['reason_code']=='source_conflict'


def test_preference_is_not_a_mandatory_blocker():
    d=change('premiere','World premieres are strongly preferred.')
    r=run(d,film=FILM.model_copy(update={'premiere_status':'Already screened at a festival'}))
    assert r['status']=='likely_fit'
    c=next(c for c in r['checks'] if c['criterion']=='premiere')
    assert c['kind']=='preference'
    assert r['total']==5


def test_generic_short_acceptance_does_not_prove_runtime():
    r=run(change('runtime','This festival accepts shorts and features, fiction and documentary films.'))
    assert r['status']=='review_required'


def test_runtime_seconds_are_not_rounded_away():
    film=FILM.model_copy(update={'runtime_minutes':30,'runtime_seconds':1})
    r=run(change('runtime','Films must be no longer than 30 minutes including credits.'),film)
    assert r['status']=='not_fit'


def test_single_category_runtime_range():
    assert run(change('runtime','Short fiction films: 10–60 minutes.'))['status']=='likely_fit'


def test_completion_inclusive_boundary():
    film=FILM.model_copy(update={'completed_on':date(2026,1,1)})
    assert run(film=film)['status']=='likely_fit'


def test_additional_subtitle_rule_cannot_disappear_behind_six_passes():
    data=candidate(additional_rules=[{'criterion':'subtitles','label':'English subtitles','source_id':'S1','quote':'Films must have English subtitles.'}])
    r=run(data);assert r['status']=='review_required';assert r['total']==7
    assert run(data,film=FILM.model_copy(update={'subtitles':['French']}))['status']=='not_fit'
    assert run(data,film=FILM.model_copy(update={'subtitles':['English']}))['status']=='likely_fit'


def test_validator_does_not_mutate_profile_or_source():
    data=candidate();before=deepcopy(data);run(data);assert data==before


def test_subminute_runtime_and_limits():
    assert Film.model_validate({**FILM.model_dump(),'runtime_minutes':0,'runtime_seconds':30}).exact_minutes==.5
    with pytest.raises(ValueError):Film.model_validate({**FILM.model_dump(),'runtime_minutes':0,'runtime_seconds':0})
    with pytest.raises(ValueError):Film.model_validate({**FILM.model_dump(),'runtime_seconds':60})


@pytest.mark.parametrize('wording', ['Short Fiction (10 minutes to 60 minutes)', 'Short fiction: 10–60 minutes.'])
def test_live_category_range_wordings(wording):
    assert run(change('runtime', wording))['status'] == 'likely_fit'


@pytest.mark.parametrize('month', ['September', 'Sept.', 'Sep'])
def test_september_dates_do_not_break_full_month_name(month):
    assert extract_dates(f'Completed after {month} 1, 2026.')[0][0] == date(2026, 9, 1)


def test_procedural_kind_cannot_hide_expired_deadline():
    data = change('deadline', 'Submission deadline: August 1, 2026.')
    data['deadline'] = '2026-08-01'
    data['checks'][-1]['kind'] = 'procedural'
    assert run(data)['status'] == 'not_fit'


@pytest.mark.parametrize('quote,accepted', [
    ('Submission fee: USD 45.', True),
    ('Submission fee: USD 145.', False),
    ('No screening fee is paid. Submission awards total USD 45.', False),
    ('Entry fee: CAD 45.', False),
])
def test_fee_is_entry_specific_and_matches_currency_amount(quote, accepted):
    data = candidate(fee={'amount': 45, 'currency': 'USD', 'tier': 'Regular', 'source_id': 'S1', 'quote': quote})
    source = Source(id='S1', title='Example Festival 2027 Shorts', url='https://festival.example/rules', excerpts=list(QUOTES.values())+[quote])
    result = validate_assessment(Assessment.model_validate({'festivals': [data]}), [source], TODAY, FILM)[0]
    assert (result['fee'] is not None) == accepted


def test_shooting_rule_is_separate_from_production_country():
    data = change('country', 'The films must be shot in India or Nepal.')
    result = run(data, film=FILM.model_copy(update={'shooting_countries': ['India']}))
    checks = {c['criterion']: c for c in result['checks']}
    assert checks['country']['status'] == 'unknown'
    assert checks['shooting_location']['status'] == 'met'


def test_qualified_programming_statement_retains_thematic_gap():
    result = run(change('genre', 'The festival showcases fiction films which speak to our political present.'))
    assert next(c for c in result['checks'] if c['criterion'] == 'genre')['status'] == 'met'
    assert next(c for c in result['checks'] if c['criterion'] == 'theme')['kind'] == 'requirement'
    assert result['status'] == 'review_required'


def test_shooting_exclusion_cannot_pass_on_country_presence():
    data = candidate(additional_rules=[{'criterion': 'shooting_location', 'label': 'Shooting', 'source_id': 'S1', 'quote': 'Films must not be shot in India.'}])
    result = run(data, film=FILM.model_copy(update={'shooting_countries': ['India']}))
    assert result['status'] != 'likely_fit'


def test_mixed_preference_cannot_soften_online_exclusion():
    quote = 'Unreleased productions receive priority. Productions released online in India will not be considered.'
    assert rule_kind(quote, 'preference') == 'requirement'


def test_named_short_clause_does_not_apply_to_long_fiction():
    quote = '3) Long Fiction (above 60 minutes, no upper limit) 4) Short Fiction (10 minutes to 60 minutes)'
    assert runtime_rule(quote, 18, 'Short Fiction')[0] == 'met'
    assert runtime_rule(quote, 75, 'Long Fiction')[0] == 'unknown'
    assert runtime_rule(quote, 18)[0] == 'unknown'


def test_submission_round_keeps_completion_month_window():
    data = change('deadline', 'Submission Deadline (for productions with a completion date between October 2025 and September 2026): October 1, 2026')
    assert run(data)['deadline'] == '2026-10-01'
    later = FILM.model_copy(update={'completed_on': date(2026, 11, 1)})
    assert run(data, film=later)['deadline'] is None


def test_unknown_check_does_not_repeat_invented_film_facts():
    data = change('premiere', 'Priority is given to films having a Kolkata premiere.')
    check = next(c for c in data['checks'] if c['criterion'] == 'premiere')
    check.update(status='unknown', explanation='The filmmaker did not supply premiere status.')
    result = next(c for c in run(data)['checks'] if c['criterion'] == 'premiere')
    assert result['status'] == 'unknown'
    assert 'did not supply' not in result['explanation']
