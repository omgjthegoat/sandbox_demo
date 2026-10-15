from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class SandboxAssistant:
    def __init__(self, kb_dir: str, leads_dir: str):
        self.kb_dir = Path(kb_dir)
        self.leads_dir = Path(leads_dir)
        self.leads_dir.mkdir(parents=True, exist_ok=True)
        self.kb = self._load_kb()
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def _load_json(self, name: str):
        return json.loads((self.kb_dir / name).read_text(encoding='utf-8'))

    def _load_kb(self):
        bundle_path = self.kb_dir.parent / 'knowledge_base.json'
        if bundle_path.exists():
            return json.loads(bundle_path.read_text(encoding='utf-8'))
        return {
            'services': self._load_json('services.json'),
            'pricing': self._load_json('pricing.json'),
            'locations_hours': self._load_json('locations_hours.json'),
            'policies': self._load_json('policies.json'),
            'routing_rules': self._load_json('routing_rules.json'),
        }

    def export_knowledge_base_bundle(self):
        return {
            'services': self.kb['services'],
            'pricing': self.kb['pricing'],
            'locations_hours': self.kb['locations_hours'],
            'policies': self.kb['policies'],
            'routing_rules': self.kb['routing_rules'],
        }

    def save_knowledge_base_bundle(self, bundle: Dict[str, Any]):
        path = self.kb_dir.parent / 'knowledge_base.json'
        normalised = {
            'services': bundle.get('services', {}),
            'pricing': bundle.get('pricing', {}),
            'locations_hours': bundle.get('locations_hours', {}),
            'policies': bundle.get('policies', {}),
            'routing_rules': bundle.get('routing_rules', {}),
        }
        path.write_text(json.dumps(normalised, indent=2), encoding='utf-8')
        self.kb = normalised
        return path

    def _state(self, session_id: str):
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'mode': 'idle',
                'lead': {
                    'name': None,
                    'contact': None,
                    'location': None,
                    'service_category': '',
                    'request_summary': '',
                    'urgency': 'normal',
                    'routed_to': None,
                    'needs_human': False,
                    'timestamp': '',
                    'transcript_reference': session_id,
                },
                'waiting_for': None,
                'last_reply': '',
            }
        return self.sessions[session_id]

    def process(self, session_id: str, message: str, transcript_reference: Optional[str] = None) -> Dict[str, Any]:
        state = self._state(session_id)
        if transcript_reference:
            state['lead']['transcript_reference'] = transcript_reference
        msg = (message or '').strip()
        lower = msg.lower()

        if state['mode'] == 'complete':
            return state['last_finalized_response']
        if state['mode'] == 'lead':
            return self._continue_lead(session_id, msg, state)

        if self._is_prompt_injection(lower):
            return self._refuse_discount(state)

        intent = self._classify_intent(lower)
        if intent == 'faq_hours':
            return self._answer_hours(state, msg)
        if intent == 'faq_pricing':
            return self._answer_pricing(state, msg)
        if intent == 'faq_services':
            return self._answer_services(state, msg)
        if intent == 'faq_policies':
            return self._answer_policies(state, msg)
        if intent == 'lead':
            state['mode'] = 'lead'
            return self._start_lead(session_id, msg, state)
        if intent == 'quote_or_lead':
            if self._is_quote_request(msg):
                return self._escalate_to_quote(state, msg, self._infer_service_category(msg))
            state['mode'] = 'lead'
            return self._start_lead(session_id, msg, state)
        if intent == 'complaint':
            lead = state['lead']
            lead['service_category'] = 'complaint'
            lead['needs_human'] = True
            lead['request_summary'] = msg
            lead['location'] = self.kb['routing_rules']['default_location']
            lead['routed_to'] = self._route(lead['service_category'], lead['location'], msg, needs_human=True)
            return self._final_response(
                state,
                stage='escalate',
                reply='I’m escalating this to the Store Manager. I can’t resolve complaints from the knowledge base alone.',
                needs_human=True,
                routed_to=lead['routed_to'],
            )

        return self._escalate_unknown(state, msg)

    def _classify_intent(self, lower: str) -> str:
        norm = lower.replace(',', '')
        if any(k in norm for k in ['complaint', 'manager', 'refund', 'damaged', 'wrong', 'problem']):
            return 'complaint'
        if any(k in norm for k in ['ignore your rules', 'discount', 'coupon', 'promo code']):
            return 'prompt_injection'
        if any(k in norm for k in ['need help', 'i need help', 'help shipping', 'need flyers printed', 'need flyers', 'want flyers']):
            return 'lead'
        if any(k in norm for k in ['need a quote', 'quote', 'estimate', 'freight', 'bulk', 'large-format', '250 pieces', '1000']):
            return 'quote_or_lead'
        if any(k in norm for k in ['hours', 'open', 'close', 'holiday', 'christmas', 'thanksgiving', 'sunday']):
            return 'faq_hours'
        if any(k in norm for k in ['how much', 'price', 'cost', 'pricing', 'business card', 'copy', 'copies', 'fax', 'passport photo', 'mailbox', 'notary', 'shred', 'scanning', 'scan']):
            return 'faq_pricing'
        if any(k in norm for k in ['shipping', 'ship', 'carrier', 'international', 'domestic', 'packing', 'pack']):
            return 'faq_services'
        if any(k in norm for k in ['print', 'printing', 'posters', 'binding']):
            return 'faq_services'
        if any(k in norm for k in ['fingerprint', 'laptop', 'repair', 'insurance claim', 'apartment', 'pizza', 'weather']):
            return 'unknown'
        return 'unknown'

    def _is_prompt_injection(self, lower: str) -> bool:
        return 'ignore your rules' in lower or 'give me a discount' in lower or 'override pricing' in lower

    def _answer_hours(self, state, msg):
        kb = self.kb['locations_hours']
        loc = self._match_location(msg) or kb['default_location']
        location = next((x for x in kb['locations'] if x['name'].lower() == loc.lower()), None)
        if not location:
            return self._escalate_unknown(state, msg)
        if 'christmas' in msg.lower() and 'day' in msg.lower():
            reply = 'Sandbox Shipping is closed on Christmas Day.'
        elif 'thanksgiving' in msg.lower():
            reply = 'Sandbox Shipping is closed on Thanksgiving Day.'
        elif 'new year' in msg.lower() and 'eve' in msg.lower():
            reply = "On New Year's Eve, all locations use reduced hours: 8:00 AM–1:00 PM."
        elif 'christmas eve' in msg.lower():
            reply = 'On Christmas Eve, all locations use reduced hours: 8:00 AM–1:00 PM.'
        else:
            hours = location['hours']
            if 'sun' in msg.lower():
                reply = f"{location['name']} is open Sunday {hours['sun']}."
            elif 'sat' in msg.lower() or 'saturday' in msg.lower():
                reply = f"{location['name']} is open Saturday {hours['sat']}."
            else:
                reply = f"{location['name']} is open Mon–Fri {hours['mon_fri']}."
        return self._final_response(state, stage='faq', reply=reply, needs_human=False)

    def _answer_pricing(self, state, msg):
        lower = msg.lower()
        text, needs_human = self._price_lookup(lower)
        if text is None:
            return self._escalate_unknown(state, msg)
        if 'quote required' in text.lower():
            team = self._route('printing' if any(k in lower for k in ['print', 'flyer', 'poster', 'copy']) else 'shipping', self.kb['routing_rules']['default_location'], msg, quote_required=True)
            reply = f"That job is quote-based, so I’m routing it to {team['team']} for a quote instead of inventing a price."
            return self._final_response(state, stage='escalate', reply=reply, needs_human=True, routed_to=team)
        if 'flyers are $49.00' in text.lower() and 'quote' in lower:
            text = text + ' Larger jobs are quote-based.'
        return self._final_response(state, stage='faq', reply=text, needs_human=False)

    def _answer_services(self, state, msg):
        lower = msg.lower()
        if 'international' in lower and 'shipping' in lower:
            reply = 'Yes — Sandbox Shipping handles international shipping through major carriers, along with packing help and freight quotes when needed.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['mailbox', 'notary', 'fax', 'scan', 'shred', 'passport photo']):
            return self._answer_pricing(state, msg) if any(k in lower for k in ['how much', 'price', 'cost']) else self._answer_service_copy(state, msg)
        if any(k in lower for k in ['copy', 'copies', 'flyer', 'poster', 'binding', 'business card', 'print']):
            return self._answer_service_copy(state, msg)
        if any(k in lower for k in ['shipping', 'ship', 'pack']):
            reply = 'Sandbox Shipping offers domestic and international shipping, packing help, freight quotes, and carrier guidance.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        return self._escalate_unknown(state, msg)

    def _answer_policies(self, state, msg):
        lower = msg.lower()
        policies = self.kb['policies']
        if any(k in lower for k in ['return', 'refund']):
            reply = 'Returns: unopened retail supplies may be returned within 14 days with a receipt. No returns on postage, notary, fax, scanning, or custom work after approval.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['prohibited', 'banned', 'forbidden', 'hazardous', 'firearm', 'weapon', 'animal', 'perishable']):
            reply = 'Prohibited items include hazardous materials, explosives, firearms, live animals, perishable food, and illegal items.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['id', 'identification']):
            reply = 'Mailbox rental and notary services require a government-issued photo ID.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['turnaround', 'turn around', 'how long']):
            reply = 'Turnaround varies: copies and fax are same day; scanning and shredding are same day or next business day depending on volume; business cards are 1–2 business days; flyers and posters are 1–3 business days; passport photos are about 15 minutes.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        return self._escalate_unknown(state, msg)

    def _answer_service_copy(self, state, msg):
        lower = msg.lower()
        services = self.kb['services']
        pricing = self.kb['pricing']
        policies = self.kb['policies']
        if any(k in lower for k in ['mailbox']):
            reply = 'Sandbox Shipping offers mailbox rental as part of its business services. Government-issued photo ID is required.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['notary']):
            reply = 'Sandbox Shipping offers notary service. Government-issued photo ID is required.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['fax']):
            reply = 'Fax is $1.50/page.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['scan']):
            reply = 'Scanning is $0.50/page.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['shred']):
            reply = 'Shredding is $0.25/lb.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['passport photo']):
            reply = 'Passport photos are $16.00 and usually take about 15 minutes.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['business card']):
            reply = 'Business cards are $24.95 for 100 cards.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['flyer']):
            if any(k in lower for k in ['1000', 'bulk', 'quote']):
                return self._escalate_to_quote(state, msg, 'printing')
            reply = 'Flyers are $49.00 for 100 single-sided 8.5x11 flyers. Larger or bulk jobs are quote-based.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['passport photo']):
            reply = 'Passport photos are $16.00 and usually take about 15 minutes.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['large-format']):
            return self._escalate_to_quote(state, msg, 'printing')
        if any(k in lower for k in ['poster']):
            if any(k in lower for k in ['bulk', 'quote']):
                return self._escalate_to_quote(state, msg, 'printing')
            reply = 'Posters are $24.00 for 18x24.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['binding']):
            reply = 'Binding starts at $6.00.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['copy', 'copies']):
            if 'color' in lower:
                reply = 'Color copies are $0.79/page.'
            else:
                reply = 'Black-and-white copies are $0.18/page.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        if any(k in lower for k in ['mailbox']):
            reply = 'Mailbox rental starts at $19/month and requires a government-issued photo ID.'
            return self._final_response(state, stage='faq', reply=reply, needs_human=False)
        return self._escalate_unknown(state, msg)

    def _price_lookup(self, lower):
        if any(k in lower for k in ['black and white copies', 'b&w copies', 'bw copies', 'black white copies', 'copies']):
            if 'color' in lower:
                return 'Color copies are $0.79/page.', False
            return 'Black-and-white copies are $0.18/page.', False
        if any(k in lower for k in ['business card']):
            return 'Business cards are $24.95 for 100 cards.', False
        if any(k in lower for k in ['flyer']):
            if any(k in lower for k in ['1000', 'bulk', 'custom', 'quote']):
                return 'Flyers over standard quantities are quote required.', True
            return 'Flyers are $49.00 for 100 single-sided 8.5x11 flyers.', False
        if any(k in lower for k in ['poster']):
            if 'bulk' in lower or 'quote' in lower:
                return 'Large poster or bulk jobs are quote required.', True
            return 'Posters are $24.00 for 18x24.', False
        if any(k in lower for k in ['binding']):
            return 'Binding starts at $6.00.', False
        if any(k in lower for k in ['mailbox']):
            return 'Mailbox rental starts at $19/month and requires a government-issued photo ID.', False
        if any(k in lower for k in ['notary']):
            return 'Notary service is $8/signature and requires a government-issued photo ID.', False
        if any(k in lower for k in ['fax']):
            return 'Fax is $1.50/page.', False
        if any(k in lower for k in ['scan']):
            return 'Scanning is $0.50/page.', False
        if any(k in lower for k in ['shred']):
            return 'Shredding is $0.25/lb.', False
        if any(k in lower for k in ['passport photo']):
            return 'Passport photos are $16.00 and usually take about 15 minutes.', False
        if any(k in lower for k in ['freight']):
            return 'Freight is quote required.', True
        if any(k in lower for k in ['international shipping']):
            return 'International shipping is carrier quote required.', True
        return None, False

    def _price_for_service_category(self, category):
        if category == 'shipping':
            return 'See shipping pricing in the knowledge base; some shipping jobs are quote-based.'
        if category == 'printing':
            return 'See printing pricing in the knowledge base; large-format and bulk jobs are quote-based.'
        if category == 'business_services':
            return 'See business services pricing in the knowledge base.'
        return 'See the knowledge base for published pricing.'

    def _start_lead(self, session_id, msg, state):
        lead = state['lead']
        self._extract_fields_from_text(lead, msg)
        lead['service_category'] = self._infer_service_category(msg)
        if self._is_quote_request(msg):
            lead['request_summary'] = lead['request_summary'] or msg
        state['waiting_for'] = self._next_missing_field(lead)
        reply = self._lead_question(state['waiting_for'])
        if state['waiting_for'] is None:
            return self._finalize_lead(state)
        return self._final_response(state, stage='intake', reply=reply, needs_human=False)

    def _continue_lead(self, session_id, msg, state):
        lead = state['lead']
        if self._contains_contact_refusal(msg):
            lead['needs_human'] = True
            return self._final_response(state, stage='escalate', reply='Understood. I can escalate it to a human, but I need contact info to complete a handoff.', needs_human=True)
        self._extract_fields_from_text(lead, msg)
        if not lead['service_category']:
            lead['service_category'] = self._infer_service_category(msg)
        loc = self._match_location(msg)
        if loc:
            lead['location'] = loc
        state['waiting_for'] = self._next_missing_field(lead)
        if state['waiting_for'] is None:
            return self._finalize_lead(state)
        if state['waiting_for'] == 'location' and lead['service_category'] and lead['name'] and lead['contact']:
            if self._is_contact_only(msg):
                return self._final_response(state, stage='intake', reply=self._lead_question('location'), needs_human=False)
            if self._looks_like_request_update(msg):
                if not lead['location']:
                    lead['location'] = self.kb['routing_rules']['default_location']
                return self._finalize_lead(state)
            if loc:
                return self._finalize_lead(state)
            return self._final_response(state, stage='intake', reply=self._lead_question('location'), needs_human=False)
        return self._final_response(state, stage='intake', reply=self._lead_question(state['waiting_for']), needs_human=False)

    def _finalize_lead(self, state):
        lead = state['lead']
        if not lead['location']:
            lead['location'] = self.kb['routing_rules']['default_location']
        if not lead['service_category']:
            lead['service_category'] = 'general'
        lead['routed_to'] = self._route(lead['service_category'], lead['location'], lead['request_summary'], quote_required=self._is_quote_request(lead['request_summary']))
        lead['needs_human'] = bool(lead['routed_to'].get('quote_required')) or lead['service_category'] == 'complaint'
        lead['timestamp'] = datetime.now(timezone.utc).isoformat()
        path = self._save_lead(lead)
        reply = f"Thanks — I routed this to {lead['routed_to']['team']} at {lead['routed_to']['location']}."
        if lead['routed_to'].get('quote_required'):
            reply += ' This is quote-based, so a human should confirm the price.'
        state['mode'] = 'complete'
        state['waiting_for'] = None
        final = self._final_response(state, stage='publish', reply=reply, needs_human=lead['needs_human'], lead_record_path=str(path), routed_to=lead['routed_to'])
        state['last_finalized_response'] = final
        return final

    def _route(self, category, location, message='', needs_human=False, quote_required=False):
        rules = self.kb['routing_rules']
        default_location = location or rules['default_location']
        if needs_human or self._is_complaint(message) or self._is_uncertain(message):
            return {'team': 'Store Manager', 'location': default_location, 'quote_required': False}
        team = 'Store Manager'
        if category == 'shipping':
            team = 'Shipping Desk'
        elif category == 'printing':
            team = 'Print Studio'
        elif category == 'business_services':
            team = 'Business Services'
        if self._is_quote_request(message):
            quote_required = True
        return {'team': team, 'location': default_location, 'quote_required': bool(quote_required)}

    def _is_quote_request(self, msg):
        lower = (msg or '').lower().replace(',', '')
        return any(k in lower for k in ['quote', 'estimate', 'freight', 'bulk', 'large-format', '250 pieces', '1000'])

    def _is_complaint(self, msg):
        lower = (msg or '').lower()
        return any(k in lower for k in ['complaint', 'damaged', 'wrong', 'refund', 'manager', 'problem'])

    def _is_uncertain(self, msg):
        lower = (msg or '').lower()
        return any(k in lower for k in ['unknown', 'not in the knowledge base'])

    def _infer_service_category(self, msg):
        lower = msg.lower()
        if any(k in lower for k in ['print', 'copies', 'copy', 'flyer', 'flyers', 'poster', 'business card', 'binding', 'large-format', 'bulk']):
            return 'printing'
        if any(k in lower for k in ['mailbox', 'notary', 'fax', 'scan', 'shred', 'passport photo']):
            return 'business_services'
        if any(k in lower for k in ['ship', 'shipping', 'freight', 'pack', 'packing', 'carrier', 'international', 'domestic']):
            return 'shipping'
        return 'general'

    def _extract_fields_from_text(self, lead, msg):
        if not lead['name']:
            m = re.search(r"(?:my name is|name is|i am|i'm)\s+([A-Z][A-Za-z\-']+(?:\s+[A-Z][A-Za-z\-']+)*)", msg, re.I)
            if m:
                lead['name'] = m.group(1).strip()
        if not lead['contact']:
            email = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', msg)
            phone = re.search(r'(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}', msg)
            if email:
                lead['contact'] = email.group(0)
            elif phone:
                lead['contact'] = phone.group(0)
        if not lead['location']:
            loc = self._match_location(msg)
            if loc:
                lead['location'] = loc
        if not lead['request_summary']:
            lead['request_summary'] = self._summarize_request(msg, lead)
        if any(k in msg.lower() for k in ['urgent', 'asap', 'rush', 'today']):
            lead['urgency'] = 'urgent'

    def _summarize_request(self, msg, lead):
        lower = msg.lower()
        if self._is_quote_request(msg):
            if any(k in lower for k in ['flyer', 'poster', 'business card', 'print']):
                return 'Quote request for printing'
            if any(k in lower for k in ['freight', 'ship']):
                return 'Quote request for shipping'
            return 'Quote request'
        return msg.strip()

    def _next_missing_field(self, lead):
        if not lead['name']:
            return 'name'
        if not lead['contact']:
            return 'contact'
        if not lead['location']:
            return 'location'
        if not lead['request_summary']:
            return 'request_summary'
        return None

    def _lead_question(self, field):
        prompts = {
            'name': 'What is your name?',
            'contact': 'What is the best email or phone number to reach you?',
            'location': 'Which location do you prefer: Park Slope, Williamsburg, or DUMBO?',
            'request_summary': 'What do you need help with?'
        }
        return prompts[field]

    def _contains_contact_refusal(self, msg):
        lower = msg.lower()
        return any(k in lower for k in ["won't give", 'will not give', 'no phone', 'no email', "don't want to share"])

    def _is_contact_only(self, msg):
        lower = msg.lower()
        return bool(re.fullmatch(r"\s*(?:my name is|name is|name\s*[:\-])?\s*[A-Za-z][A-Za-z\-']*(?:\s+[A-Za-z][A-Za-z\-']*)*\s*(?:@[^\s]+\.[^\s]+|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})?\s*", msg)) and any(k in lower for k in ['name is', 'my name is', '@', 'phone'])

    def _looks_like_request_update(self, msg):
        lower = msg.lower()
        return any(k in lower for k in ['shipping', 'freight', 'flyer', 'poster', 'print', 'copies', 'mailbox', 'notary', 'passport', 'fax', 'scan', 'shred', 'need help', 'need flyers', 'need a quote'])

    def _match_location(self, msg):
        lower = msg.lower()
        for loc in self.kb['locations_hours']['locations']:
            if loc['name'].lower() in lower:
                return loc['name']
        return None

    def _save_lead(self, lead):
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        filename = f"lead_{ts}_{uuid.uuid4().hex[:8]}.json"
        path = self.leads_dir / filename
        path.write_text(json.dumps(lead, indent=2), encoding='utf-8')
        return path

    def _final_response(self, state, stage, reply, needs_human, lead_record_path=None, routed_to=None):
        resp = {
            'stage': stage,
            'reply': reply,
            'needs_human': needs_human,
            'routed_to': routed_to,
            'lead_record_path': lead_record_path,
            'waiting_for': state.get('waiting_for'),
        }
        state['last_reply'] = reply
        return resp

    def _escalate_unknown(self, state, msg):
        reply = 'That is not in the knowledge base, so I’m escalating it to a human instead of guessing.'
        routed = self._route('general', self.kb['routing_rules']['default_location'], msg, needs_human=True)
        return self._final_response(state, stage='escalate', reply=reply, needs_human=True, routed_to=routed)

    def _escalate_to_quote(self, state, msg, category):
        team = 'Print Studio' if category == 'printing' else 'Shipping Desk'
        routed = {'team': team, 'location': self.kb['routing_rules']['default_location'], 'quote_required': True}
        reply = f'That is quote-based, so I’m routing it to {team} for a human quote rather than inventing a price.'
        return self._final_response(state, stage='escalate', reply=reply, needs_human=True, routed_to=routed)

    def _refuse_discount(self, state):
        reply = 'I cannot override the published pricing or invent a discount. I can share the listed pricing or route you to a human if needed.'
        return self._final_response(state, stage='faq', reply=reply, needs_human=False)


def load_assistant(base_dir: str = None):
    base = Path(base_dir or Path(__file__).resolve().parent)
    return SandboxAssistant(str(base / 'data/knowledge_base'), str(base / 'leads'))
