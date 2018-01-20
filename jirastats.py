#!/usr/bin/env python3

import urllib
import requests
import json
import os

JS_USERNAME = os.getenv('JS_USERNAME')
JS_PASSWORD = os.getenv('JS_PASSWORD')
JS_BASE_URL = os.getenv('JS_BASE_URL')
JS_STORYPOINTS_FIELD = os.getenv('JS_STORYPOINTS_FIELD', 'customfield_10008')
JS_TIMEESTIMATE_FIELD = 'aggregatetimeoriginalestimate'
JS_AUTH = (JS_USERNAME, JS_PASSWORD)
JS_HEADERS = {'Content-Type': 'application/json', 'Accept': 'application/json'}
JS_MAX_RESULTS = 999


def jira_post(url, data):
    return requests.post(url, headers=JS_HEADERS, auth=JS_AUTH, data=data)


def jira_get(url):
    return requests.get(url, headers=JS_HEADERS, auth=JS_AUTH)


def jira_search(jql, max_results=50):
    search_params = {'jql': jql, 'maxResults': max_results, 'fields': [JS_STORYPOINTS_FIELD, JS_TIMEESTIMATE_FIELD]}
    search_url = JS_BASE_URL + '/rest/api/2/search'
    resp = jira_post(search_url, json.dumps(search_params))
    return resp


def get_project_name_from_key(key):
    resp = jira_get(JS_BASE_URL + '/rest/api/2/project/' + key)
    if resp.status_code == 200:
        resp = json.loads(resp.text)
        if 'name' in resp.keys():
            return resp['name']
    else:
        print(resp.status_code)
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
        print(resp.status_code)
    return None


def calculate_time_estimate(resp):
    total_time = 0
    if 'issues' in resp.keys():
        for issue in resp['issues']:
            if 'fields' in issue:
                if JS_TIMEESTIMATE_FIELD in issue['fields'].keys():
                    orig_est = issue['fields'][JS_TIMEESTIMATE_FIELD]
                    if orig_est is not None:
                        total_time += int(orig_est)
    return total_time


def get_time_estimate(jql):
    resp = jira_search(jql, JS_MAX_RESULTS)
    if resp.status_code == 200:
        return calculate_time_estimate(json.loads(resp.text))
    else:
        print(resp.status_code)
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
            resp = jira_get(JS_BASE_URL + '/rest/greenhopper/1.0/sprintquery/' + str(rapid_view_id) + '?includeHistoricSprints=true&includeFutureSprints=true')
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
                        print(resp.status_code)
                average_velocity = int(sum(story_points) / max(1, len(story_points)))
                return average_velocity
            else:
                print(resp.status_code)
    else:
        print(resp.status_code)
    return None


def get_project_stats(project_key, get_estimate_fn=get_story_points):
    jql = 'project=' + project_key
    total_est = get_estimate_fn(jql)
    jql = 'project=' + project_key + ' AND resolution != Unresolved'
    resolved_est = get_estimate_fn(jql)
    project_name = get_project_name_from_key(project_key)
    if project_name is None:
        average_velocity = None
    else:
        average_velocity = get_average_velocity(project_name)
    return (total_est, resolved_est, average_velocity)


def main():
    print(get_project_stats(''))
    print(get_project_stats(''))
    print(get_project_stats('', get_time_estimate))


if __name__ == '__main__':
    main()
