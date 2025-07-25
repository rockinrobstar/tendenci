from builtins import str
import random
from datetime import datetime, timedelta
from operator import or_
from functools import reduce
import json

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AnonymousUser, User
from django.template import Node, Library, TemplateSyntaxError, Variable
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe

from tendenci.apps.events.models import Event, Registrant, Type
from tendenci.apps.events.utils import (registration_earliest_time,
                                        registration_has_started,
                                        registration_has_ended,)
from tendenci.apps.base.template_tags import ListNode, parse_tag_kwargs
from tendenci.apps.perms.utils import get_query_filters
from tendenci.apps.events.forms import EventSimpleSearchForm
from tendenci.apps.site_settings.utils import get_setting


register = Library()


@register.inclusion_tag("events/badge.html", takes_context=True)
def badge(context, registrant, display='front'):
    context.update({
        "registrant": registrant,
        "display": display,
    })
    return context

@register.inclusion_tag("events/credits.html", takes_context=True)
def credits_form_display(context, event, credit_forms, user):
    context.update({
        "event": event,
        "credit_forms": credit_forms,
        "user": user,
    })
    return context


@register.inclusion_tag("events/child_events.html", takes_context=True)
def child_events_display(context, event, user=None, edit=False):
    context.update({
        "child_events": event.get_child_events_by_permission(user, edit),
        "edit": edit,
    })
    return context


@register.inclusion_tag("events/credits_review.html", takes_context=True)
def review_and_edit_credits(context, event):
    context.update({
        "parent_event": event,
        "events": event.events_with_credits,
    })
    return context


@register.inclusion_tag("events/options.html", takes_context=True)
def event_options(context, user, event):
    context.update({
        "opt_object": event,
        "user": user
    })
    return context


@register.inclusion_tag("events/nav.html", takes_context=True)
def event_nav(context, user, event=None):
    display_attendees = False
    if event:
        display_attendees = event.can_view_registrants(user)
    context.update({
        "nav_object": event,
        "user": user,
        "can_view_attendees": display_attendees,
        "today": datetime.today()
    })
    return context


@register.inclusion_tag("events/search-form.html", takes_context=True)
def event_search(context):
    return context


@register.inclusion_tag("events/top_nav_items.html", takes_context=True)
def event_current_app(context, user, event=None):
    context.update({
        "app_object": event,
        "user": user
    })
    return context


@register.inclusion_tag("events/reg8n/check_in_modal.html", takes_context=True)
def event_check_in_modal(context, registrant_id, form, message, is_session_set):
    context.update({
        "registrant_id": registrant_id, 
        "form": form, 
        "message": message,
        "is_session_set": is_session_set
        })
    return context


@register.inclusion_tag("events/clone_modal.html", takes_context=True)
def event_clone_modal(context, event):
    context.update({"event": event})
    return context


@register.inclusion_tag("events/reg8n/cancel_modal.html", takes_context=True)
def event_cancel_modal(
        context, event, hash=None, registrant=None, registrants=[], registration=None):
    if not registrant and not registrants:
        raise Exception("Must include at least one registrant or a list of registrants")

    reg = registrant if registrant else registrants[0]
    cancellation_fee = event.registration_configuration.get_cancellation_fee(reg.amount)

    if len(registrants) > 1:
        cancellation_fee *= len(registrants)

    allow_refunds_setting = get_setting("module", "events", "allow_refunds")
    allow_refunds = allow_refunds_setting and allow_refunds_setting != "No"

    context.update({
        "event": event,
        "registrant": registrant,
        "registration": registration,
        "cancellation_fee": cancellation_fee,
        "allow_refunds": allow_refunds,
    })
    return context


@register.inclusion_tag("events/registrants/options.html", takes_context=True)
def registrant_options(context, user, registrant):
    context.update({
        "opt_object": registrant,
        "user": user
    })
    return context


@register.inclusion_tag("events/registrants/search-form.html", takes_context=True)
def registrant_search(context, event=None):
    context.update({
        "event": event
    })
    return context


@register.inclusion_tag("events/registrants/global-search-form.html", takes_context=True)
def global_registrant_search(context):
    return context


@register.inclusion_tag('events/reg8n/registration_pricing.html', takes_context=True)
def registration_pricing_and_button(context, event, user):
    limit = event.get_limit()
    spots_taken = 0
    registration = event.registration_configuration

    pricing = registration.get_available_pricings(user, is_strict=False)
    pricing = pricing.order_by('position', '-price')

    reg_started = registration_has_started(event, pricing=pricing)
    reg_ended = registration_has_ended(event, pricing=pricing)
    earliest_time = registration_earliest_time(event, pricing=pricing)

    # spots taken
    if limit > 0:
        spots_taken, spots_available = event.get_spots_status()
    else:
        spots_taken, spots_available = (-1, -1)

    is_registrant = False
    registrant = None
    # check if user has already registered
    if hasattr(user, 'registrant_set'):
        registrants = user.registrant_set.filter(
            registration__event=event).filter(cancel_dt__isnull=True)
        registrant_count = registrants.count()

        is_registrant = registrant_count > 0
        if registrant_count == 1:
            registrant = registrants.first()

    context.update({
        'now': datetime.now(),
        'event': event,
        'limit': limit,
        'spots_taken': spots_taken,
        'spots_available': spots_available,
        'registration': registration,
        'reg_started': reg_started,
        'reg_ended': reg_ended,
        'earliest_time': earliest_time,
        'pricing': pricing,
        'user': user,
        'is_registrant': is_registrant,
        'registrant': registrant,
    })

    return context


@register.inclusion_tag('events/files_view.html', takes_context=True)
def file_detail(context, attachment):
    context.update({
        "file": attachment
    })
    return context


class EventListNode(Node):
    def __init__(self, day, type_slug, ordering, group, search_text, context_var):
        self.day = Variable(day)
        self.type_slug = Variable(type_slug)
        if search_text:
            self.search_text = Variable(search_text)
        else:
            self.search_text = ''
        if group:
            self.group = Variable(group)
        else:
            self.group = None
        self.ordering = ordering
        if ordering:
            self.ordering = ordering.replace("'", '')
        self.context_var = context_var

    def render(self, context):

        request = context.get('request', None)

        # make sure data in query and cat are valid
        form = EventSimpleSearchForm(request.GET)
        if form.is_valid():
            cat = form.cleaned_data.get('search_category', None)
            query = form.cleaned_data.get('q', None)
        else:
            cat = None
            query = ''

        day = self.day.resolve(context)
        type_slug = self.type_slug.resolve(context)
        if self.search_text:
            search_text = self.search_text.resolve(context)
        else:
            search_text = ''
        if self.group:
            group = self.group.resolve(context)
        else:
            group = None

        types = Type.objects.filter(slug=type_slug)

        type = None
        if types:
            type = types[0]

        day = datetime(day.year, day.month, day.day)
        weekday = day.strftime('%a')

        #one day offset so we can get all the events on that day
        bound = timedelta(hours=23, minutes=59)

        start_dt = day+bound
        end_dt = day

        filters = get_query_filters(context['user'], 'events.view_event')
        events = Event.objects.filter(filters).filter(start_dt__lte=start_dt, end_dt__gte=end_dt).distinct().extra(select={'hour': 'extract( hour from start_dt )'}).extra(select={'minute': 'extract( minute from start_dt )'})
        events = events.filter(enable_private_slug=False)

        if type:
            events = events.filter(type=type)

        if group:
            events = events.filter(groups__in=[group])

        if search_text:
            events = events.filter(Q(title__icontains=search_text) | Q(description__icontains=search_text))

        if weekday == 'Sun' or weekday == 'Sat':
            events = events.filter(on_weekend=True)

        if self.ordering == "single_day":
            events = events.order_by('-priority', 'hour', 'minute')
        else:
            if self.ordering:
                events = events.order_by(self.ordering)
            else:
                events = events.order_by('-priority', 'start_dt')

        if cat == 'priority':
            events = events.filter(**{cat : True })
        elif query and cat:
            events = events.filter(**{cat : query})

        context[self.context_var] = events
        return ''


@register.tag
def event_list(parser, token):
    """
    Example: {% event_list day as events %}
             {% event_list day type as events %}
             {% event_list day type 'start_dt' as events %}
             {% event_list day type 'start_dt' group as events %}
             {% event_list day type 'start_dt' group search_text as events %}
    """
    bits = token.split_contents()
    type_slug = None
    ordering = None
    group = None
    search_text = ''

    if len(bits) != 4 and len(bits) != 5 and len(bits) != 6 and len(bits) != 7 and len(bits) != 8:
        message = '%s tag requires 4 or 5 or 6 or 7 or 8 arguments' % bits[0]
        raise TemplateSyntaxError(_(message))

    if len(bits) == 4:
        day = bits[1]
        context_var = bits[3]

    if len(bits) == 5:
        day = bits[1]
        type_slug = bits[2]
        context_var = bits[4]

    if len(bits) == 6:
        day = bits[1]
        type_slug = bits[2]
        ordering = bits[3]
        context_var = bits[5]
        
    if len(bits) == 7:
        day = bits[1]
        type_slug = bits[2]
        ordering = bits[3]
        group = bits[4]
        context_var = bits[6]

    if len(bits) == 8:
        day = bits[1]
        type_slug = bits[2]
        ordering = bits[3]
        group = bits[4]
        search_text = bits[5]
        context_var = bits[7]

    return EventListNode(day, type_slug, ordering, group, search_text, context_var)


class UserRegistrationNode(Node):

    def __init__(self, user, event, context_var):
        self.user = Variable(user)
        self.event = Variable(event)
        self.context_var = context_var

    def render(self, context):

        user = self.user.resolve(context)
        event = self.event.resolve(context)

        registration = None
        if not isinstance(user, AnonymousUser):
            registrants = user.registrant_set.filter(registration__event=event, cancel_dt=None)
            if registrants.count() == 1:
                registration = registrants.first().registration

        context[self.context_var] = registration
        return ''

@register.tag
def user_registration(parser, token):
    """
    Example: {% user_registration user event as registration %}
    """
    bits = token.split_contents()

    if len(bits) != 5:
        message = '%s tag requires 5 arguments' % bits[0]
        raise TemplateSyntaxError(_(message))

    user = bits[1]
    event = bits[2]
    context_var = bits[4]

    return UserRegistrationNode(user, event, context_var)

class IsRegisteredUserNode(Node):

    def __init__(self, user, event, context_var):
        self.user = Variable(user)
        self.event = Variable(event)
        self.context_var = context_var

    def render(self, context):

        user = self.user.resolve(context)
        event = self.event.resolve(context)

        if isinstance(user, AnonymousUser):
            exists = False
        else:
            exists = Registrant.objects.filter(
                registration__event=event,
                email=user.email,
                cancel_dt=None,
            ).exists()

        context[self.context_var] = exists
        return ''

@register.tag
def is_registered_user(parser, token):
    """
    Example: {% is_registered_user user event as registered_user %}
    """
    bits = token.split_contents()

    if len(bits) != 5:
        message = '%s tag requires 5 arguments' % bits[0]
        raise TemplateSyntaxError(_(message))

    user = bits[1]
    event = bits[2]
    context_var = bits[4]

    return IsRegisteredUserNode(user, event, context_var)


class ListEventsNode(ListNode):
    model = Event

    def __init__(self, context_var, *args, **kwargs):
        self.context_var = context_var
        self.kwargs = kwargs

        if not self.model:
            raise AttributeError(_('Model attribute must be set'))
        if not issubclass(self.model, models.Model):
            raise AttributeError(_('Model attribute must derive from Model'))
        if not hasattr(self.model.objects, 'search'):
            raise AttributeError(_('Model.objects does not have a search method'))

    def render(self, context):
        tags = u''
        query = u''
        user = AnonymousUser()
        limit = 3
        order = 'next_upcoming'
        event_type = ''
        group = u''
        start_dt = u''
        registered_only = False
        registration_open = False

        randomize = False

        if 'start_dt' in self.kwargs:
            try:
                start_dt = datetime.strptime(self.kwargs['start_dt'].replace('"', '').replace("'", ''), '%m/%d/%Y-%H:%M')
            except ValueError:
                pass

        if 'random' in self.kwargs:
            randomize = bool(self.kwargs['random'])

        if 'tags' in self.kwargs:
            try:
                tags = Variable(self.kwargs['tags'])
                tags = str(tags.resolve(context))
            except:
                tags = self.kwargs['tags']

            tags = tags.replace('"', '')
            tags = tags.split(',')

        if 'user' in self.kwargs:
            try:
                user = Variable(self.kwargs['user'])
                user = user.resolve(context)
            except:
                user = self.kwargs['user']
                if user == "anon" or user == "anonymous":
                    user = AnonymousUser()
        else:
            # check the context for an already existing user
            # and see if it is really a user object
            if 'user' in context:
                if isinstance(context['user'], User):
                    user = context['user']

        if 'limit' in self.kwargs:
            try:
                limit = Variable(self.kwargs['limit'])
                limit = limit.resolve(context)
            except:
                limit = self.kwargs['limit']

        limit = int(limit)

        if 'query' in self.kwargs:
            try:
                query = Variable(self.kwargs['query'])
                query = query.resolve(context)
            except:
                query = self.kwargs['query']  # context string

        if 'order' in self.kwargs:
            try:
                order = Variable(self.kwargs['order'])
                order = order.resolve(context)
            except:
                order = self.kwargs['order']

        if 'type' in self.kwargs:
            try:
                event_type = Variable(self.kwargs['type'])
                event_type = event_type.resolve(context)
            except:
                event_type = self.kwargs['type']

        if 'group' in self.kwargs:
            try:
                group = Variable(self.kwargs['group'])
                group = str(group.resolve(context))
            except:
                group = self.kwargs['group']

            try:
                group = int(group)
            except:
                group = None
        if 'registered_only' in self.kwargs:
            try:
                registered_only = Variable(self.kwargs['registered_only'])
                registered_only = registered_only.resolve(context)
            except:
                registered_only = self.kwargs['registered_only']
        if 'registration_open' in self.kwargs:
            try:
                registration_open = Variable(self.kwargs['registration_open'])
                registration_open = registration_open.resolve(context)
            except:
                registration_open = self.kwargs['registration_open']

        filters = get_query_filters(user, 'events.view_event')
        items = Event.objects.filter(filters)
        if user.is_authenticated:
            if not user.profile.is_superuser:
                items = items.distinct()

        if event_type:
            if isinstance(event_type, int):
                items = items.filter(type__id=event_type)
            elif isinstance(event_type, str):
                if ',' in event_type:
                    items = items.filter(type__name__in=event_type.split(','))
                else:
                    items = items.filter(type__name__iexact=event_type)

        if tags:  # tags is a comma delimited list
            # this is fast; but has one hole
            # it finds words inside of other words
            # e.g. "prev" is within "prevent"
            tag_queries = [Q(tags__iexact=t.strip()) for t in tags]
            tag_queries += [Q(tags__istartswith=t.strip()+",") for t in tags]
            tag_queries += [Q(tags__iendswith=", "+t.strip()) for t in tags]
            tag_queries += [Q(tags__iendswith=","+t.strip()) for t in tags]
            tag_queries += [Q(tags__icontains=", "+t.strip()+",") for t in tags]
            tag_queries += [Q(tags__icontains=","+t.strip()+",") for t in tags]
            tag_query = reduce(or_, tag_queries)
            items = items.filter(tag_query)

        if hasattr(self.model, 'group') and group:
            items = items.filter(groups=group)
        if hasattr(self.model, 'groups') and group:
            items = items.filter(groups__in=[group])

        objects = []

        if start_dt:
            items = items.filter(start_dt__gte=start_dt)

        # exclude private events
        items = items.filter(enable_private_slug=False)

        # if order is not specified it sorts by relevance
        if order:
            if order == "next_upcoming":
                if not start_dt:
                    # Removed seconds and microseconds so we can cache the query better
                    now = datetime.now().replace(second=0, microsecond=0)
                    items = items.filter(start_dt__gt=now)
                items = items.order_by("start_dt", '-priority')
            elif order == "current_and_upcoming":
                if not start_dt:
                    now = datetime.now().replace(second=0, microsecond=0)
                    items = items.filter(Q(start_dt__gt=now) | Q(end_dt__gt=now))
                items = items.order_by("start_dt", '-priority')
            elif order == "current_and_upcoming_by_hour":
                now = datetime.now().replace(second=0, microsecond=0)
                today = datetime.now().replace(second=0, hour=0, minute=0, microsecond=0)
                tomorrow = today + timedelta(days=1)
                items = items.filter(Q(start_dt__lte=tomorrow) & Q(end_dt__gte=today)).extra(select={'hour': 'extract( hour from start_dt )'}).extra(select={'minute': 'extract( minute from start_dt )'}).extra(where=["extract( hour from start_dt ) >= %s"], params=[now.hour])
                items = items.distinct()
                items = items.order_by('hour', 'minute', '-priority')
            elif order == "past":
                items = items.filter(start_dt__lt=datetime.now())
                items = items.order_by("-start_dt", '-priority')
            else:
                items = items.order_by(order)

        if user and user.is_authenticated and registered_only:
            items = [item for item in items if item.is_registrant_user(user)]

        if registration_open:
            items = [item for item in items if registration_has_started(item) and not registration_has_ended(item)]

        if randomize:
            items = list(items)
            objects = random.sample(items, min(len(items), limit))
        else:
            objects = items[:limit]

        context[self.context_var] = objects
        return ""


@register.tag
def list_events(parser, token):
    """
    Used to pull a list of :model:`events.Event` items.

    Usage::

        {% list_events as [varname] [options] %}

    Be sure the [varname] has a specific name like ``events_sidebar`` or
    ``events_list``. Options can be used as [option]=[value]. Wrap text values
    in quotes like ``tags="cool"``. Options include:

        ``limit``
           The number of items that are shown. **Default: 3**
        ``order``
           The order of the items. Custom options include ``next_upcoming`` for the
           events starting after now, and ``current_and_upcoming`` for events going on
           as well as upcoming. **Default: Next Upcoming by date**
        ``user``
           Specify a user to only show public items to all. **Default: Viewing user**
        ``type``
           The type of the event. Allows comma separated multiple types. e.g. type="General Meeting,Annual Events"
        ``tags``
           The tags required on items to be included.
        ``group``
           The group id associated with items to be included.
        ``random``
           Use this with a value of true to randomize the items included.
        ``start_dt``
           Specify the date that events should start after to be shown. MUST be in the format 1/20/2013-06:45

    Example::

        {% list_events as events_list limit=5 tags="cool" %}
        {% for event in events_list %}
            {{ event.title }}
        {% endfor %}
    """
    args, kwargs = [], {}
    bits = token.split_contents()
    context_var = bits[2]

    if len(bits) < 3:
        message = "'%s' tag requires more than 3" % bits[0]
        raise TemplateSyntaxError(_(message))

    if bits[1] != "as":
        message = "'%s' second argument must be 'as" % bits[0]
        raise TemplateSyntaxError(_(message))

    kwargs = parse_tag_kwargs(bits)

    if 'order' not in kwargs:
        kwargs['order'] = 'next_upcoming'

    return ListEventsNode(context_var, *args, **kwargs)


@register.simple_tag
def render_json_ld(structured_data):
    return mark_safe(f'<script type="application/ld+json">{json.dumps(structured_data)}</script>')
    