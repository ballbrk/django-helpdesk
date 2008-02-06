#!/usr/bin/python
"""
Jutda Helpdesk - A Django powered ticket tracker for small enterprise.

(c) Copyright 2008 Jutda. All Rights Reserved. See LICENSE for details.

scripts/escalate_tickets.py - Easy way to escalate tickets based on their age, 
                              designed to be run from Cron or similar.
"""
from datetime import datetime, timedelta, date
from django.db.models import Q
from helpdesk.models import Queue, Ticket, FollowUp, EscalationExclusion, TicketChange
from helpdesk.lib import send_multipart_mail
import sys, getopt

def escalate_tickets(queues, verbose):
    """ Only include queues with escalation configured """
    queryset = Queue.objects.filter(escalate_days__isnull=False).exclude(escalate_days=0)
    if queues:
        queryset = queryset.filter(slug__in=queues)
    
    for q in queryset:
        last = date.today() - timedelta(days=q.escalate_days)
        today = date.today()
        workdate = last

        days = 0

        while workdate < today:
            if EscalationExclusion.objects.filter(date=workdate).count() == 0:
                days += 1
            workdate = workdate + timedelta(days=1)


        req_last_escl_date = date.today() - timedelta(days=days)

        if verbose:
            print "Processing: %s" % q
        
        for t in q.ticket_set.filter(Q(status=Ticket.OPEN_STATUS) | Q(status=Ticket.REOPENED_STATUS)).exclude(priority=1).filter(Q(on_hold__isnull=True) | Q(on_hold=False)).filter(Q(last_escalation__lte=req_last_escl_date) | Q(last_escalation__isnull=True)):
            t.last_escalation = datetime.now()
            t.priority -= 1
            t.save()
        
            context = {
                'ticket': t,
                'queue': queue,
            }

            if t.submitter_email:
                send_multipart_mail('helpdesk/emails/submitter_escalated', context, '%s %s' % (t.ticket, t.title), t.submitter_email, t.queue.from_address)
            
            if t.queue.updated_ticket_cc:
                send_multipart_mail('helpdesk/emails/cc_escalated', context, '%s %s' % (t.ticket, t.title), t.queue.updated_ticket_cc, t.queue.from_address)
            
            if t.assigned_to:
                send_multipart_mail('helpdesk/emails/owner_escalated', context, '%s %s' % (t.ticket, t.title), t.assigned_to, t.queue.from_address)

            if verbose:
                print "  - Esclating %s from %s>%s" % (t.ticket, t.priority+1, t.priority)

            f = FollowUp(
                ticket = t,
                title = 'Ticket Escalated',
                date=datetime.now(),
                public=True,
                comment='Ticket escalated after %s days' % q.escalate_days,
            )
            f.save()

            tc = TicketChange(
                followup = f,
                field = 'Priority',
                old_value = t.priority + 1,
                new_value = t.priority,
            )
            tc.save()

def usage():
    print "Options:"
    print " --queues, -q: Queues to include (default: all). Use queue slugs"
    print " --verbose, -v: Display a list of dates excluded"

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'q:v', ['queues=', 'verbose'])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    verbose = False
    queue_slugs = None
    queues = []
    
    for o, a in opts:
        if o in ('-v', '--verbose'):
            verbose = True
        if o in ('-q', '--queues'):
            queue_slugs = a
    
    if queue_slugs is not None:
        queue_set = queue_slugs.split(',')
        for queue in queue_set:
            try:
                q = Queue.objects.get(slug__exact=queue)
            except:
                print "Queue %s does not exist." % queue
                sys.exit(2)
            queues.append(queue)

    escalate_tickets(queues=queues, verbose=verbose)
