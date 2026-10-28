"""Synthetic metadata only; executable directly, no pytest/conftest or backend."""
import importlib.util
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'scripts/beta_v2_transcript_provenance.py'
spec = importlib.util.spec_from_file_location('transcript_provenance', SOURCE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

DECISION = '2030-01-02T10:00:00Z'  # Synthetic fixed replay clock, never wall-clock gating.
EARLY = '2030-01-02T08:00:00Z'
PUBLIC = '2030-01-02T08:30:00Z'
SEEN = '2030-01-02T09:00:00Z'
FUTURE = '2030-01-02T11:00:00Z'


def clock(at, field, basis='source_metadata', version='v1'):
    binding = m.SourceVersion('synthetic', 'call-1', version, 'a'*64, 'synthetic:version/' + version)
    return m.Clock(at, field, 'synthetic:receipt/' + field, binding, basis)


def record():
    return m.TranscriptMetadata(
        m.SourceVersion('synthetic', 'call-1', 'v1', 'a' * 64, 'synthetic:version/v1'),
        creation=clock(EARLY, 'created'), event=clock(EARLY, 'call_start'),
        publication=clock(PUBLIC, 'published'),
        observed=clock(SEEN, 'first_seen', 'collector_observation'))


class ProvenanceTests(unittest.TestCase):
    def check_status(self, row, status, reason=None, decision=DECISION):
        result = m.validate_availability(row, decision_at=decision)
        self.assertEqual(result.status, status)
        self.assertEqual(result.historical_eligible, status == 'eligible')
        if reason:
            self.assertIn(reason, result.reasons)
        return result

    def test_exact_version_historical_metadata(self):
        result = self.check_status(record(), 'eligible')
        self.assertEqual(result.usable_from, '2030-01-02T09:00:00+00:00')
        self.assertEqual(result.metadata.publication.at, PUBLIC)

    def test_creation_and_event_are_not_publication_or_observation(self):
        row = replace(record(), publication=m.Clock(), observed=m.Clock())
        result = self.check_status(row, 'unknown', 'no_version_bound_observation')
        self.assertIsNone(result.usable_from)
        self.assertIsNone(result.to_dict()['metadata']['publication']['at'])

    def test_acquisition_only_is_prospective(self):
        row = replace(record(), publication=m.Clock(), observed=clock(SEEN, 'acquired_at', 'acquisition'))
        result = self.check_status(row, 'prospective-only', 'acquisition_not_historical_availability')
        self.assertEqual(result.usable_from, '2030-01-02T09:00:00+00:00')

    def test_older_publication_does_not_backdate_late_acquisition(self):
        row = replace(record(), observed=clock(SEEN, 'acquired_at', 'acquisition'))
        result = self.check_status(row, 'prospective-only')
        self.assertNotEqual(result.usable_from, PUBLIC)

    def test_observed_without_publication_retains_unknown(self):
        self.check_status(replace(record(), publication=m.Clock()), 'prospective-only', 'publication_unknown')

    def test_publication_without_observation_is_unknown(self):
        self.check_status(replace(record(), observed=m.Clock()), 'unknown')

    def test_acquisition_cannot_be_labeled_publication(self):
        self.check_status(replace(record(), publication=clock(PUBLIC, 'acquired_at', 'acquisition')),
                          'unknown', 'acquisition_cannot_establish_publication')

    def test_each_future_version_clock_refuses(self):
        for name, basis in [('creation', 'source_metadata'), ('revision', 'source_metadata'),
                            ('publication', 'source_metadata'), ('observed', 'collector_observation')]:
            with self.subTest(name=name):
                result = self.check_status(replace(record(), **{name: clock(FUTURE, name, basis)}),
                                           'unknown', name + '_after_decision')
                self.assertIsNone(result.usable_from)

    def test_future_acquisition_cannot_qualify_prior_decision(self):
        self.check_status(replace(record(), observed=clock(FUTURE, 'acquired', 'acquisition')),
                          'unknown', 'observed_after_decision')

    def test_event_time_does_not_substitute_for_version_time(self):
        self.check_status(replace(record(), event=clock(FUTURE, 'scheduled_event')), 'eligible',
                          'event_after_decision_not_an_availability_clock')

    def test_timezone_offsets_and_exact_boundary(self):
        row = replace(record(), observed=clock('2030-01-02T18:00:00+08:00', 'first_seen', 'collector_observation'))
        self.check_status(row, 'eligible')

    def test_naive_date_only_and_malformed_clocks_refuse(self):
        for value in ('2030-01-02', '2030-01-02T08:00:00', 'bad', ''):
            with self.subTest(value=value):
                self.check_status(replace(record(), publication=clock(value, 'published')),
                                  'unknown', 'publication_invalid_or_ambiguous_clock')

    def test_invalid_decision_clock_refuses(self):
        for value in ('2030-01-02', '2030-01-02T10:00:00', 'bad'):
            self.check_status(record(), 'unknown', 'invalid_decision_clock', decision=value)

    def test_provenance_and_version_bindings_are_required(self):
        for change, reason in [({'evidence_ref': None}, 'publication_missing_provenance'),
                               ({'source_field': None}, 'publication_missing_provenance'),
                               ({'source_version': replace(record().version, version_id='v2')}, 'publication_source_version_mismatch'),
                               ({'basis': 'guess'}, 'publication_invalid_evidence_basis')]:
            self.check_status(replace(record(), publication=replace(record().publication, **change)), 'unknown', reason)

    def test_source_identity_and_digest_required(self):
        for field, value in [('source_id', ''), ('record_id', ''), ('version_id', ''),
                             ('evidence_ref', ''), ('content_sha256', 'not-a-digest')]:
            self.check_status(replace(record(), version=replace(record().version, **{field: value})), 'unknown')

    def test_matching_version_label_cannot_borrow_another_source_record_or_digest(self):
        for field, value in [('source_id', 'another-source'), ('record_id', 'another-call'),
                             ('content_sha256', 'b'*64), ('evidence_ref', 'another:version-receipt')]:
            binding = replace(record().version, **{field: value})
            row = replace(record(), observed=replace(record().observed, source_version=binding))
            self.check_status(row, 'unknown', 'observed_source_version_mismatch')

    def test_invalid_evidence_basis_type_is_an_explicit_refusal(self):
        self.check_status(replace(record(), observed=replace(record().observed, basis=[])),
                          'unknown', 'observed_invalid_evidence_basis')

    def test_contradictory_ordering_refuses(self):
        for name in ('creation', 'revision'):
            self.check_status(replace(record(), **{name: clock('2030-01-02T09:30:00Z', name)}),
                              'unknown', name + '_after_observed')
        self.check_status(replace(record(), revision=clock('2030-01-02T07:00:00Z', 'revision')),
                          'unknown', 'revision_before_creation')

    def test_updated_version_cannot_rewrite_or_borrow_prior_receipt(self):
        old = record()
        prior = self.check_status(old, 'eligible').to_dict()
        new = replace(old, version=replace(old.version, version_id='v2', content_sha256='b'*64),
                      supersedes_version_id='v1')
        self.check_status(new, 'unknown', 'observed_source_version_mismatch')
        self.assertEqual(self.check_status(old, 'eligible').to_dict(), prior)
        self.assertEqual(old.version.version_id, 'v1')
        with self.assertRaises(FrozenInstanceError):
            old.version.version_id = 'v2'

    def test_future_correction_not_original_version_available(self):
        old = record()
        new = m.TranscriptMetadata(replace(old.version, version_id='v2', evidence_ref='synthetic:version/v2'),
            creation=clock(EARLY, 'created', version='v2'),
            publication=clock(FUTURE, 'revision_released', version='v2'),
            revision=clock(FUTURE, 'revision_created', version='v2'),
            observed=clock(FUTURE, 'first_seen', 'collector_observation', 'v2'),
            supersedes_version_id='v1')
        self.check_status(new, 'unknown', 'revision_after_decision')
        self.check_status(new, 'eligible', decision='2030-01-02T12:00:00Z')
        self.check_status(old, 'eligible')

    def test_unknown_nonessential_clocks_are_not_fabricated(self):
        row = replace(record(), creation=m.Clock(), event=m.Clock())
        result = self.check_status(row, 'eligible')
        self.assertIsNone(dict(result.normalized_clocks)['creation'])

    def test_self_supersession_refuses(self):
        self.check_status(replace(record(), supersedes_version_id='v1'), 'unknown', 'self_superseding_version')

    def test_metadata_only_contract_and_serializable_output(self):
        with self.assertRaises(TypeError):
            m.TranscriptMetadata(record().version, text='not accepted')
        output = json.loads(json.dumps(self.check_status(record(), 'eligible').to_dict()))
        self.assertEqual(output['scope'], 'transcript_version_temporal_provenance_only')
        self.assertEqual(output['metadata']['version']['content_sha256'], 'a'*64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
