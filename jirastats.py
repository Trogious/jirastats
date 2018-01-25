#!/usr/bin/env python3

import urllib
import requests
import json
import os
import datetime
import sys

JS_USERNAME = os.getenv('JS_USERNAME')
JS_PASSWORD = os.getenv('JS_PASSWORD')
JS_BASE_URL = os.getenv('JS_BASE_URL')
JS_STORYPOINTS_FIELD = os.getenv('JS_STORYPOINTS_FIELD', 'customfield_10008')
JS_OUTPUT_JSON_FILE = os.getenv('JS_OUTPUT_JSON_FILE')
JS_TIMEESTIMATE_FIELD = 'timeoriginalestimate'
JS_AUTH = (JS_USERNAME, JS_PASSWORD)
JS_HEADERS = {'Content-Type': 'application/json', 'Accept': 'application/json'}
JS_MAX_RESULTS = 999
JS_DATE_SEPARATOR = '-'
JS_CONFIG_ISSUE_NAME = 'ReportsConfig'
JS_CONFIG_FIELD = 'description'


def log(log_item):
    sys.stderr.write(datetime.datetime.now().isoformat(sep='_')[:19] + ': ' + str(log_item) + '\n')
    sys.stderr.flush()


def jira_post(url, data):
    return requests.post(url, headers=JS_HEADERS, auth=JS_AUTH, data=data)


def jira_get(url):
    return requests.get(url, headers=JS_HEADERS, auth=JS_AUTH)


def jira_search(jql, max_results=50, fields=[JS_STORYPOINTS_FIELD, JS_TIMEESTIMATE_FIELD]):
    search_params = {'jql': jql, 'maxResults': max_results, 'fields': fields}
    resp = jira_post(JS_BASE_URL + '/rest/api/2/search', json.dumps(search_params))
    return resp


def get_project_name_from_key(key):
    resp = jira_get(JS_BASE_URL + '/rest/api/2/project/' + key)
    if resp.status_code == 200:
        resp = json.loads(resp.text)
        if 'name' in resp.keys():
            return resp['name']
    else:
        log(resp.status_code)
    return None


def calculate_story_points(resp):
    total_sp = 0
    if 'issues' in resp.keys():
        for issue in resp['issues']:
            if 'fields' in issue.keys():
                if JS_STORYPOINTS_FIELD in issue['fields'].keys():
                    story_points = issue['fields'][JS_STORYPOINTS_FIELD]
                    if story_points is not None:
                        total_sp += int(story_points)
    return total_sp


def get_story_points(jql):
    resp = jira_search(jql, JS_MAX_RESULTS)
    if resp.status_code == 200:
        return calculate_story_points(json.loads(resp.text))
    else:
        log(resp.status_code)
    return None


def calculate_time_estimate(resp):
    total_time_in_seconds = 0
    if 'issues' in resp.keys():
        for issue in resp['issues']:
            if 'fields' in issue:
                if JS_TIMEESTIMATE_FIELD in issue['fields'].keys():
                    orig_est = issue['fields'][JS_TIMEESTIMATE_FIELD]
                    if orig_est is not None:
                        total_time_in_seconds += int(orig_est)
    return int(total_time_in_seconds / 3600 / 8)


def get_time_estimate(jql):
    resp = jira_search(jql, JS_MAX_RESULTS)
    if resp.status_code == 200:
        return calculate_time_estimate(json.loads(resp.text))
    else:
        log(resp.status_code)
    return None


def get_rapidview_id(resp, project_name):
    if 'views' in resp.keys():
        for view in resp['views']:
            if project_name.strip().lower() == view['name'].strip().lower():
                return view['id']
    return None


def get_closed_sprint_ids(resp):
    ids = []
    if 'sprints' in resp.keys():
        for sprint in resp['sprints']:
            if sprint['state'].strip().lower() == 'closed':
                ids.append(sprint['id'])
    return ids


def get_sprint_completed_sp(resp):
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


def get_average_velocity(project_name):
    resp = jira_get(JS_BASE_URL + '/rest/greenhopper/1.0/rapidviews/list')
    if resp.status_code == 200:
        rapid_view_id = get_rapidview_id(json.loads(resp.text), project_name)
        if rapid_view_id is not None:
            resp = jira_get(JS_BASE_URL + '/rest/greenhopper/1.0/sprintquery/' + str(rapid_view_id) + '?includeHistoricsprints=true&includeFuturesprints=true')
            if resp.status_code == 200:
                sprint_ids = get_closed_sprint_ids(json.loads(resp.text))
                story_points = []
                for sprint_id in sprint_ids:
                    resp = jira_get(JS_BASE_URL + '/rest/greenhopper/1.0/rapid/charts/sprintreport?rapidViewId=' + str(rapid_view_id) + '&sprintId=' + str(sprint_id))
                    if resp.status_code == 200:
                        sp = get_sprint_completed_sp(json.loads(resp.text))
                        if sp is not None:
                            story_points.append(sp)
                    else:
                        log(resp.status_code)
                average_velocity = int(sum(story_points) / max(1, len(story_points)))
                return (average_velocity, rapid_view_id)
            else:
                log(resp.status_code)
    else:
        log(resp.status_code)
    return None


def parse_config(config):
    keys = config.keys()
    if 'start_date' in keys and 'end_date' in keys:
        if 'estimate_type' in keys and 'time' == config['estimate_type'].strip().lower():
            get_estimate_fn = get_time_estimate
            estimate_type = 'time'
        else:
            get_estimate_fn = get_story_points
            estimate_type = 'story_points'
        if 'title' in keys:
            title = config['title']
        else:
            title = None
        if 'milestones' in keys and len(config['milestones']) > 0:
            milestones = config['milestones']
        else:
            milestones = None
        if estimate_type == 'story_points':
            url_postfix = ' AND issueFunction IN aggregateExpression(Total, "storyPoints.sum()")'
        else:
            url_postfix = ' AND issueFunction IN aggregateExpression(Total, "originalEstimate.sum()")'
        return {'start_date': config['start_date'], 'end_date': config['end_date'], 'get_estimate_fn': get_estimate_fn,
                'estimate_type': estimate_type, 'title': title, 'url_postfix': url_postfix, 'milestones': milestones}
    return None


def get_project_config(config_key):
    resp = jira_get(JS_BASE_URL + '/rest/api/2/issue/' + config_key + '?fields=' + JS_CONFIG_FIELD)
    if resp.status_code == 200:
        issue = json.loads(resp.text)
        if 'fields' in issue.keys() and JS_CONFIG_FIELD in issue['fields'].keys():
            descr = issue['fields'][JS_CONFIG_FIELD]
            for line in [l.strip() for l in descr.splitlines()]:
                if len(line) > 0:
                    if line.find('#') < 0:
                        try:
                            return parse_config(json.loads(line))
                        except Exception as e:
                            log(e)
    else:
        log(resp.status_code)
    return None


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


def get_project_stats(config_key):
    config = get_project_config(config_key)
    get_estimate_fn = config['get_estimate_fn']
    project_key = config_key.strip().split('-')[0]
    jql = 'project=' + project_key
    total_est = get_estimate_fn(jql)
    total_est_url = get_jira_url_issues(jql, config['url_postfix'])
    jql = 'project=' + project_key + ' AND resolution != Unresolved'
    resolved_est = get_estimate_fn(jql)
    remaining_est = total_est - resolved_est
    remaining_est_url = get_jira_url_issues(jql, config['url_postfix'])
    days = get_days_for_estimates(config['start_date'], config['end_date'])
    total_estimates_to_date = []
    urls_to_date = {}
    urls_to_date['total'] = []
    for day in days:
        jql = 'project=' + project_key + ' AND createdDate <= "' + day + '"'
        total_est_to_date = get_estimate_fn(jql)
        urls_to_date['total'].append(get_jira_url_issues(jql, config['url_postfix']))
        total_estimates_to_date.append(total_est_to_date)
    resolved_estimates_to_date = []
    urls_to_date['burned'] = []
    for day in days:
        jql = 'project=' + project_key + ' AND resolution != Unresolved AND resolutiondate <= "' + day + '"'
        resolved_est_to_date = get_estimate_fn(jql)
        urls_to_date['burned'].append(get_jira_url_issues(jql, config['url_postfix']))
        resolved_estimates_to_date.append(resolved_est_to_date)
    remaining_estimates_to_date = [total_estimates_to_date[i] - resolved_estimates_to_date[i] for i in range(len(total_estimates_to_date))]
    project_name = get_project_name_from_key(project_key)
    velocity_url = None
    if project_name is None:
        average_velocity = None
    else:
        average_velocity, rapid_view_id = get_average_velocity(project_name)
        if config['estimate_type'] == 'time':
            average_velocity = int(average_velocity / 3600 / 8)
        if rapid_view_id is not None:
            velocity_url = get_jira_url_velocity(rapid_view_id)
    if config['title'] is None:
        title = project_key
    else:
        title = config['title']
    to_date = {'total_estimates': total_estimates_to_date, 'burned_estimates': resolved_estimates_to_date,
               'remaining_estimates': remaining_estimates_to_date, 'dates': days, 'urls': urls_to_date}
    stats = {'project_key': project_key, 'estimate_type': config['estimate_type'], 'total_scope_estimate': total_est, 'burned_scope_estimate': resolved_est,
             'total_scope_url': total_est_url, 'burned_scope_url': remaining_est_url, 'average_velocity': average_velocity, 'velocity_url': velocity_url,
             'remaining_scope_estimate': remaining_est, 'title': title, 'to_date': to_date, 'milestones': config['milestones']}
    return stats


def get_config_keys_for_reporting():
    jql = 'summary ~ "' + JS_CONFIG_ISSUE_NAME + '"'
    resp = jira_search(jql)
    if resp.status_code == 200:
        issues = json.loads(resp.text)
        if 'issues' in issues.keys():
            config_keys = []
            for issue in issues['issues']:
                config_key = issue['key']
                config_keys.append(config_key)
            return config_keys
    else:
        log(resp.status_code)
    return []


def main():
    keys = get_config_keys_for_reporting()
    stats_obj = {'projects': []}
    for config_key in keys:
        stats = get_project_stats(config_key)
        stats_obj['projects'].append(stats)
    stats_obj['projects'].sort(key=lambda p: p['to_date']['dates'][0])
    stats_json = json.dumps(stats_obj)
    try:
        with open(JS_OUTPUT_JSON_FILE, 'w') as f:
            f.write(stats_json)
    except OSError as e:
        log(e)
        sys.exit(e.errno)


if __name__ == '__main__':
    main()
