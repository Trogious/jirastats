#!/usr/bin/env python3

import urllib
import requests
import json
import os
import datetime
import sys
from threading import Thread, Lock

JS_USERNAME = os.getenv('JS_USERNAME')
JS_PASSWORD = os.getenv('JS_PASSWORD')
JS_BASE_URL = os.getenv('JS_BASE_URL')
JS_STORYPOINTS_FIELD = os.getenv('JS_STORYPOINTS_FIELD', 'customfield_10008')
JS_OUTPUT_JSON_FILE = os.getenv('JS_OUTPUT_JSON_FILE')
JS_ARCHIVE_ISSUE_KEY = os.getenv('JS_ARCHIVE_ISSUE_KEY')
JS_TIMEESTIMATE_FIELD = 'timeoriginalestimate'
JS_AUTH = (JS_USERNAME, JS_PASSWORD)
JS_HEADERS = {'Content-Type': 'application/json', 'Accept': 'application/json'}
JS_MAX_RESULTS = 999
JS_DATE_SEPARATOR = '-'
JS_CONFIG_ISSUE_NAME = 'ReportsConfig'
JS_CONFIG_FIELD = 'description'
JS_EXTIMATE_SP = 'story_points'
JS_ESTIMATE_MD = 'man_days'
JS_DATE_FORMAT_HISTORY = '%Y-%m-%dT%H:%M:%S'
JS_lock = Lock()


def log(log_item):
    with JS_lock:
        sys.stderr.write(datetime.datetime.now().isoformat(sep='_')[:19] + ': ' + str(log_item) + '\n')
        sys.stderr.flush()


def jira_post(url, data):
    return requests.post(url, headers=JS_HEADERS, auth=JS_AUTH, data=data)


def jira_get(url, params=None):
    return requests.get(url, headers=JS_HEADERS, auth=JS_AUTH, params=params)


def jira_search(jql, max_results=50, fields=[JS_STORYPOINTS_FIELD, JS_TIMEESTIMATE_FIELD], expand=''):
    search_params = {'jql': jql, 'maxResults': max_results, 'fields': fields, 'expand': expand}
    resp = jira_get(JS_BASE_URL + '/rest/api/2/search', search_params)
    return resp


def get_date_from_str(date_str):
    date = map(lambda x: int(x), date_str.split(JS_DATE_SEPARATOR))
    return datetime.date(*date)


def get_days_for_estimates(start_date, end_date):
    d = get_date_from_str(start_date)
    end_d = get_date_from_str(end_date)
    days = []
    while d <= end_d:
        days.append(str(d))
        d += datetime.timedelta(weeks=1)
    return days


def get_jira_url_issues(jql, postfix):
    return JS_BASE_URL + '/issues/?jql=' + urllib.parse.quote(jql + postfix)


def get_jira_url_velocity(rapid_view_id):
    return JS_BASE_URL + '/secure/RapidBoard.jspa?view=reporting&chart=velocityChart&rapidView=' + str(rapid_view_id)


def get_project_key_from_config_key(config_key):
    return config_key.strip().split('-')[0]


class StatsFetcher(Thread):
    def __init__(self, config_key, archive):
        super().__init__()
        self.config_key = config_key
        self.archive = archive
        self.project_key = get_project_key_from_config_key(self.config_key)
        self.stats = None

    def get_project_name_from_key(self, key):
        resp = jira_get(JS_BASE_URL + '/rest/api/2/project/' + key)
        if resp.status_code == 200:
            resp = json.loads(resp.text)
            if 'name' in resp.keys():
                return resp['name']
        else:
            log(resp.status_code)
        return None

    def calculate_story_points(self, resp):
        total_sp = 0
        if 'issues' in resp.keys():
            for issue in resp['issues']:
                if 'fields' in issue.keys():
                    if JS_STORYPOINTS_FIELD in issue['fields'].keys():
                        story_points = issue['fields'][JS_STORYPOINTS_FIELD]
                        if story_points is not None:
                            total_sp += int(story_points)
        return total_sp

    def get_story_points(self, jql):
        resp = jira_search(jql, JS_MAX_RESULTS)
        if resp.status_code == 200:
            return self.calculate_story_points(resp.json())
        else:
            log(resp.status_code)
        return None

    def calculate_time_estimate(self, resp):
        total_time_in_seconds = 0
        if 'issues' in resp.keys():
            for issue in resp['issues']:
                if 'fields' in issue:
                    if JS_TIMEESTIMATE_FIELD in issue['fields'].keys():
                        orig_est = issue['fields'][JS_TIMEESTIMATE_FIELD]
                        if orig_est is not None:
                            total_time_in_seconds += int(orig_est)
        return int(total_time_in_seconds / 3600 / 8)

    def get_time_estimate(self, jql):
        resp = jira_search(jql, JS_MAX_RESULTS)
        if resp.status_code == 200:
            return self.calculate_time_estimate(resp.json())
        else:
            log(resp.status_code)
        return None

    def get_rapidview_id(self, resp, project_name):
        if 'views' in resp.keys():
            for view in resp['views']:
                if view['name'].strip().lower() == project_name.strip().lower().replace('closed/', ''):
                    return view['id']
        return None

    def get_sprint_data(self, resp):
        data = []
        if 'sprints' in resp.keys():
            for sprint in resp['sprints']:
                data.append((sprint['id'], sprint['name'], sprint['state'].strip().lower() == 'closed'))
        return data

    def get_sprint_completed_sp(self, resp):
        completed_sp = None
        if 'contents' in resp.keys():
            all_issues_sp = resp['contents']['allIssuesEstimateSum']
            if 'value' in all_issues_sp.keys():
                all_issues_sp = int(all_issues_sp['value'])
                if all_issues_sp > 0:
                    completed_est = resp['contents']['completedIssuesEstimateSum']
                    if 'value' in completed_est:
                        completed_sp = int(completed_est['value'])
        return completed_sp

    def is_bug(self, issue):
        return issue['typeName'].lower() in ['bug', 'sub-bug']

    def get_issue_counts(self, contents, name):
        bugs_no = 0.0
        non_bugs_no = 0.0
        if name in contents.keys():
            for issue in contents[name]:
                if self.is_bug(issue):
                    bugs_no += 1.0
                else:
                    non_bugs_no += 1.0
        return (bugs_no, non_bugs_no)

    def get_sprint_ratios(self, resp):
        ratios = None
        if 'contents' in resp.keys():
            contents = resp['contents']
            bugs_no, non_bugs_no = self.get_issue_counts(contents, 'completedIssues')
            counts = self.get_issue_counts(contents, 'issuesNotCompletedInCurrentSprint')
            bugs_no += counts[0]
            non_bugs_no += counts[1]
            total_no = bugs_no + non_bugs_no
            if total_no < 1:
                ratio = 0.0
            else:
                ratio = float((bugs_no*100)/total_no)
            ratios = (non_bugs_no, bugs_no, ratio)
        return ratios

    def get_sprint_metrics(self, project_name):
        resp = jira_get(JS_BASE_URL + '/rest/greenhopper/1.0/rapidviews/list')
        if resp.status_code == 200:
            rapid_view_id = self.get_rapidview_id(resp.json(), project_name)
            if rapid_view_id is not None:
                resp = jira_get(JS_BASE_URL + '/rest/greenhopper/1.0/sprintquery/' + str(rapid_view_id) + '?includeHistoricsprints=true&includeFuturesprints=true')
                if resp.status_code == 200:
                    sprint_data = self.get_sprint_data(resp.json())
                    story_points = []
                    ratios = []
                    for s_data in sprint_data:
                        sprint_id, sprint_name, sprint_closed = s_data
                        resp = jira_get(JS_BASE_URL + '/rest/greenhopper/1.0/rapid/charts/sprintreport?rapidViewId=' + str(rapid_view_id) + '&sprintId=' + str(sprint_id))
                        if resp.status_code == 200:
                            if sprint_closed:
                                resp_json = resp.json()
                                sp = self.get_sprint_completed_sp(resp_json)
                                if sp is not None:
                                    story_points.append(sp)
                            ratio = self.get_sprint_ratios(resp_json)
                            if ratio is not None:
                                ratios.append({'sprint_id': sprint_id, 'sprint_name': sprint_name, 'features2bugs': ratio})
                        else:
                            log(resp.status_code)
                    average_velocity = int(sum(story_points) / max(1, len(story_points)))
                    ratios.sort(key=lambda r: r['sprint_id'])
                    return (average_velocity, rapid_view_id, ratios)
                else:
                    log(resp.status_code)
            else:
                log('cannot find rapidview')
        else:
            log(resp.status_code)
        return None

    def parse_config(self, config):
        keys = config.keys()
        if 'start_date' in keys and 'end_date' in keys:
            if 'estimate_type' in keys and JS_ESTIMATE_MD == config['estimate_type'].strip().lower():
                get_estimate_fn = self.get_time_estimate
                estimate_type = JS_ESTIMATE_MD
            else:
                get_estimate_fn = self.get_story_points
                estimate_type = JS_EXTIMATE_SP
            if 'title' in keys:
                title = config['title']
            else:
                title = None
            if 'milestones' in keys and len(config['milestones']) > 0:
                milestones = config['milestones']
            else:
                milestones = None
            if estimate_type == JS_EXTIMATE_SP:
                url_postfix = ' AND issueFunction IN aggregateExpression(Total, "storyPoints.sum()")'
            else:
                url_postfix = ' AND issueFunction IN aggregateExpression(Total, "originalEstimate.sum()")'
            return {'start_date': config['start_date'], 'end_date': config['end_date'], 'get_estimate_fn': get_estimate_fn,
                    'estimate_type': estimate_type, 'title': title, 'url_postfix': url_postfix, 'milestones': milestones}
        return None

    def get_project_config(self, config_key):
        resp = jira_get(JS_BASE_URL + '/rest/api/2/issue/' + config_key + '?fields=' + JS_CONFIG_FIELD)
        if resp.status_code == 200:
            issue = json.loads(resp.text)
            if 'fields' in issue.keys() and JS_CONFIG_FIELD in issue['fields'].keys():
                descr = issue['fields'][JS_CONFIG_FIELD]
                for line in [l.strip() for l in descr.splitlines()]:
                    if len(line) > 0:
                        if line.find('#') < 0:
                            try:
                                return self.parse_config(json.loads(line))
                            except Exception as e:
                                log(e)
        else:
            log(resp.status_code)
        return None

    def get_time_in_status(self, status, issue):
        dt = datetime.timedelta()
        length = len(issue['changelog']['histories'])
        for i in range(length):
            hs = issue['changelog']['histories'][i]
            for item in hs['items']:
                if item['field'] == 'status' and item['fromString'].upper() == status.upper() and i > 0:
                    start = datetime.datetime.strptime(hs['created'][:19], JS_DATE_FORMAT_HISTORY)
                    he = issue['changelog']['histories'][i-1]
                    end = datetime.datetime.strptime(he['created'][:19], JS_DATE_FORMAT_HISTORY)
                    dt += (start - end)
                    break
        return dt.days * 24 * 3600 + dt.seconds

    def get_times_in(self):
        jql = 'project=' + self.project_key + ' AND status in (Done)'
        time_spent = {'READY FOR CODING': 0, 'CODING': 0, 'READY FOR TESTING': 0, 'TESTING': 0, 'TESTING BLOCKED': 0}
        resp = jira_search(jql, JS_MAX_RESULTS, ['fixVersions'], 'changelog')
        if resp.status_code == 200:
            issues = resp.json()
            if 'issues' in issues.keys():
                for issue in issues['issues']:
                    for status in time_spent.keys():
                        time_spent[status] += self.get_time_in_status(status, issue)
        else:
            log(resp.status_code)
        return time_spent

    def get_project_stats(self):
        config = self.get_project_config(self.config_key)
        get_estimate_fn = config['get_estimate_fn']
        jql = 'project=' + self.project_key
        total_est = get_estimate_fn(jql)
        total_est_url = get_jira_url_issues(jql, config['url_postfix'])
        jql = 'project=' + self.project_key + ' AND resolution != Unresolved'
        resolved_est = get_estimate_fn(jql)
        remaining_est = total_est - resolved_est
        remaining_est_url = get_jira_url_issues(jql, config['url_postfix'])
        days = get_days_for_estimates(config['start_date'], config['end_date'])
        total_estimates_to_date = []
        urls_to_date = {}
        urls_to_date['total'] = []
        for day in days:
            jql = 'project=' + self.project_key + ' AND createdDate <= "' + day + '"'
            total_est_to_date = get_estimate_fn(jql)
            urls_to_date['total'].append(get_jira_url_issues(jql, config['url_postfix']))
            total_estimates_to_date.append(total_est_to_date)
        resolved_estimates_to_date = []
        urls_to_date['burned'] = []
        for day in days:
            jql = 'project=' + self.project_key + ' AND resolution != Unresolved AND resolutiondate <= "' + day + '"'
            resolved_est_to_date = get_estimate_fn(jql)
            urls_to_date['burned'].append(get_jira_url_issues(jql, config['url_postfix']))
            resolved_estimates_to_date.append(resolved_est_to_date)
        remaining_estimates_to_date = [total_estimates_to_date[i] - resolved_estimates_to_date[i] for i in range(len(total_estimates_to_date))]
        project_name = self.get_project_name_from_key(self.project_key)
        velocity_url = None
        average_velocity = None
        sprint_ratios = None
        if project_name is not None:
            sprint_metrics = self.get_sprint_metrics(project_name)
            if sprint_metrics is not None:
                average_velocity, rapid_view_id, sprint_ratios = sprint_metrics
                if config['estimate_type'] == JS_ESTIMATE_MD:
                    average_velocity = int(average_velocity / 3600 / 8)
                if rapid_view_id is not None:
                    velocity_url = get_jira_url_velocity(rapid_view_id)
            else:
                sprint_ratios = None
        if config['title'] is None:
            title = self.project_key
        else:
            title = config['title']
        to_date = {'total_estimates': total_estimates_to_date, 'burned_estimates': resolved_estimates_to_date,
                   'remaining_estimates': remaining_estimates_to_date, 'dates': days, 'urls': urls_to_date}
        times_in = self.get_times_in()
        stats = {'project_key': self.project_key, 'estimate_type': config['estimate_type'], 'total_scope_estimate': total_est, 'burned_scope_estimate': resolved_est,
                 'total_scope_url': total_est_url, 'burned_scope_url': remaining_est_url, 'average_velocity': average_velocity, 'velocity_url': velocity_url,
                 'sprint_ratios': sprint_ratios, 'times_in': times_in, 'remaining_scope_estimate': remaining_est, 'title': title, 'to_date': to_date,
                 'milestones': config['milestones']}
        return stats

    def get_archived(self):
        if 'projects' in self.archive.keys():
            projects = self.archive['projects']
            for project in projects:
                if 'project_key' in project:
                    if self.project_key.upper() == project['project_key'].upper():
                        return project
        return None

    def run(self):
        archived_stats = self.get_archived()
        if archived_stats is None:
            log('fetch ' + self.project_key)
            self.stats = self.get_project_stats()
        else:
            log('archive ' + self.project_key)
            self.stats = archived_stats


def get_config_keys_for_reporting():
    jql = 'summary ~ "' + JS_CONFIG_ISSUE_NAME + '"'
    resp = jira_search(jql)
    if resp.status_code == 200:
        issues = resp.json()
        if 'issues' in issues.keys():
            config_keys = []
            for issue in issues['issues']:
                config_key = issue['key']
                config_keys.append(config_key)
            return config_keys
    else:
        log(resp.status_code)
    return []


def get_archive(issue_key):
    if issue_key is not None:
        resp = jira_get(JS_BASE_URL + '/rest/api/2/issue/' + issue_key + '?fields=attachment')
        if resp.status_code == 200:
            issue = resp.json()
            if 'fields' in issue.keys():
                fields = issue['fields']
                if 'attachment' in fields.keys():
                    attachments = fields['attachment']
                    for attachment in attachments:
                        if attachment['filename'].lower() == 'archive.json':
                            resp = jira_get(attachment['content'])
                            if resp.status_code == 200:
                                try:
                                    return resp.json()
                                except Exception:
                                    return {}
                            else:
                                log(resp.status_code)
        else:
            log(resp.status_code)
    return {}


def main():
    keys = get_config_keys_for_reporting()
    archive = get_archive(JS_ARCHIVE_ISSUE_KEY)
    stats_obj = {'projects': []}
    fetchers = []
    for config_key in keys:
        fetcher = StatsFetcher(config_key, archive)
        fetchers.append(fetcher)
        fetcher.start()
    for fetcher in fetchers:
        fetcher.join()
        stats_obj['projects'].append(fetcher.stats)
    stats_obj['projects'].sort(key=lambda p: p['to_date']['dates'][0])
    stats_obj['generated_at'] = datetime.datetime.now().isoformat(sep=' ')[:19]
    stats_json = json.dumps(stats_obj)
    try:
        with open(JS_OUTPUT_JSON_FILE, 'w') as f:
            f.write(stats_json)
    except OSError as e:
        log(e)
        sys.exit(e.errno)


if __name__ == '__main__':
    main()
