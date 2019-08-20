import os
import shutil
import pickle
from io import StringIO
from ruamel.yaml import YAML
from difflib import SequenceMatcher
from datetime import datetime as dt
from upgrade import upgrade_yaml_file
from constants import *

# Due to performance reasons the import of attackcti is within the function that makes use of this library.


def _save_attack_data(data, path):
    """
    Save ATT&CK data to disk for the purpose of caching. Data can be STIX objects our a custom schema.
    :param data: the MITRE ATT&CK data to save
    :param path: file path to write to, including filename
    :return:
    """

    if not os.path.exists('cache/'):
        os.mkdir('cache/')
    with open(path, 'wb') as f:
        pickle.dump([data, dt.now()], f)


def load_attack_data(data_type):
    """
    Load the cached ATT&CK data from disk, if not expired (data file on disk is older then EXPIRE_TIME seconds).
    :param data_type: the desired data type, see DATATYPE_XX constants.
    :return: MITRE ATT&CK data object (STIX or custom schema)
    """
    if os.path.exists("cache/" + data_type):
        with open("cache/" + data_type, 'rb') as f:
            cached = pickle.load(f)
            write_time = cached[1]
            if not (dt.now() - write_time).total_seconds() >= EXPIRE_TIME:
                # the first item in the list contains the ATT&CK data
                return cached[0]

    from attackcti import attack_client
    mitre = attack_client()

    attack_data = None
    if data_type == DATA_TYPE_STIX_ALL_RELATIONSHIPS:
        attack_data = mitre.get_relationships()
    elif data_type == DATA_TYPE_STIX_ALL_TECH_ENTERPRISE:
        attack_data = mitre.get_enterprise_techniques()
    elif data_type == DATA_TYPE_CUSTOM_TECH_BY_GROUP:
        # First we need to know which technique references (STIX Object type 'attack-pattern') we have for all
        # groups. This results in a dict: {group_id: Gxxxx, technique_ref/attack-pattern_ref: ...}
        groups = load_attack_data(DATA_TYPE_STIX_ALL_GROUPS)
        relationships = load_attack_data(DATA_TYPE_STIX_ALL_RELATIONSHIPS)
        all_groups_relationships = []
        for g in groups:
            for r in relationships:
                if g['id'] == r['source_ref'] and r['relationship_type'] == 'uses' and \
                        r['target_ref'].startswith('attack-pattern--'):
                    # much more information on the group can be added. Only the minimal required data is now added.
                    all_groups_relationships.append(
                        {
                            'group_id': get_attack_id(g),
                            'name': g['name'],
                            'aliases': g.get('aliases', None),
                            'technique_ref': r['target_ref']
                        })

        # Now we start resolving this part of the dict created above: 'technique_ref/attack-pattern_ref'.
        # and we add some more data to the final result.
        all_group_use = []
        techniques = load_attack_data(DATA_TYPE_STIX_ALL_TECH)
        for gr in all_groups_relationships:
            for t in techniques:
                if t['id'] == gr['technique_ref']:
                    all_group_use.append(
                        {
                            'group_id': gr['group_id'],
                            'name': gr['name'],
                            'aliases': gr['aliases'],
                            'technique_id': get_attack_id(t),
                            'x_mitre_platforms': t.get('x_mitre_platforms', None),
                            'matrix': t['external_references'][0]['source_name']
                        })

        attack_data = all_group_use

    elif data_type == DATA_TYPE_STIX_ALL_TECH:
        attack_data = mitre.get_techniques()
    elif data_type == DATA_TYPE_STIX_ALL_GROUPS:
        attack_data = mitre.get_groups()
    elif data_type == DATA_TYPE_STIX_ALL_SOFTWARE:
        attack_data = mitre.get_software()
    elif data_type == DATA_TYPE_CUSTOM_TECH_BY_SOFTWARE:
        # First we need to know which technique references (STIX Object type 'attack-pattern') we have for all software
        # This results in a dict: {software_id: Sxxxx, technique_ref/attack-pattern_ref: ...}
        software = load_attack_data(DATA_TYPE_STIX_ALL_SOFTWARE)
        relationships = load_attack_data(DATA_TYPE_STIX_ALL_RELATIONSHIPS)
        all_software_relationships = []
        for s in software:
            for r in relationships:
                if s['id'] == r['source_ref'] and r['relationship_type'] == 'uses' and \
                        r['target_ref'].startswith('attack-pattern--'):
                    # much more information (e.g. description, aliases, platform) on the software can be added to the
                    # dict if necessary. Only the minimal required data is now added.
                    all_software_relationships.append({'software_id': get_attack_id(s), 'technique_ref': r['target_ref']})

        # Now we start resolving this part of the dict created above: 'technique_ref/attack-pattern_ref'
        techniques = load_attack_data(DATA_TYPE_STIX_ALL_TECH)
        all_software_use = []
        for sr in all_software_relationships:
            for t in techniques:
                if t['id'] == sr['technique_ref']:
                    # much more information on the technique can be added to the dict. Only the minimal required data
                    # is now added (i.e. resolving the technique ref to an actual ATT&CK ID)
                    all_software_use.append({'software_id': sr['software_id'], 'technique_id': get_attack_id(t)})

        attack_data = all_software_use

    elif data_type == DATA_TYPE_CUSTOM_SOFTWARE_BY_GROUP:
        # First we need to know which software references (STIX Object type 'malware' or 'tool') we have for all
        # groups. This results in a dict: {group_id: Gxxxx, software_ref/malware-tool_ref: ...}
        groups = load_attack_data(DATA_TYPE_STIX_ALL_GROUPS)
        relationships = load_attack_data(DATA_TYPE_STIX_ALL_RELATIONSHIPS)
        all_groups_relationships = []
        for g in groups:
            for r in relationships:
                if g['id'] == r['source_ref'] and r['relationship_type'] == 'uses' and \
                        (r['target_ref'].startswith('tool--') or r['target_ref'].startswith('malware--')):
                    # much more information on the group can be added. Only the minimal required data is now added.
                    all_groups_relationships.append(
                        {
                            'group_id': get_attack_id(g),
                            'name': g['name'],
                            'aliases': g.get('aliases', None),
                            'software_ref': r['target_ref']
                        })

        # Now we start resolving this part of the dict created above: 'software_ref/malware-tool_ref'.
        # and we add some more data to the final result.
        all_group_use = []
        software = load_attack_data(DATA_TYPE_STIX_ALL_SOFTWARE)
        for gr in all_groups_relationships:
            for s in software:
                if s['id'] == gr['software_ref']:
                    all_group_use.append(
                        {
                            'group_id': gr['group_id'],
                            'name': gr['name'],
                            'aliases': gr['aliases'],
                            'software_id': get_attack_id(s),
                            'x_mitre_platforms': s.get('x_mitre_platforms', None),
                            'matrix': s['external_references'][0]['source_name']
                        })
        attack_data = all_group_use

    elif data_type == DATA_TYPE_STIX_ALL_ENTERPRISE_MITIGATIONS:
        attack_data = mitre.get_enterprise_mitigations()

    elif data_type == DATA_TYPE_STIX_ALL_MOBILE_MITIGATIONS:
        attack_data = mitre.get_mobile_mitigations()

    _save_attack_data(attack_data, "cache/" + data_type)

    return attack_data


def init_yaml():
    _yaml = YAML()
    _yaml.Representer.ignore_aliases = lambda *args: True  # disable anchors/aliases
    return _yaml


def _get_base_template(name, description, stage, platform, sorting):
    """
    Prepares a base template for the json layer file that can be loaded into the MITRE ATT&CK Navigator.
    More information on the version 2.1 layer format:
    https://github.com/mitre/attack-navigator/blob/master/layers/LAYERFORMATv2_1.md
    :param name: name
    :param description: description
    :param stage: stage (act | prepare)
    :param platform: platform
    :param sorting: sorting
    :return: layer template dictionary
    """
    layer = dict()
    layer['name'] = name
    layer['version'] = '2.1'
    layer['domain'] = 'mitre-enterprise'
    layer['description'] = description

    if platform == 'all':
        platform = ['windows', 'linux', 'mac']
    else:
        platform = [platform.lower()]

    if stage == 'attack':
        layer['filters'] = {'stages': ['act'], 'platforms': platform}
    else:
        layer['filters'] = {'stages': ['prepare'], 'platforms': platform}

    layer['sorting'] = sorting
    layer['viewMode'] = 0
    layer['hideDisable'] = False
    layer['techniques'] = []

    layer['showTacticRowBackground'] = False
    layer['tacticRowBackground'] = COLOR_TACTIC_ROW_BACKGRND
    layer['selectTechniquesAcrossTactics'] = True
    return layer


def get_layer_template_groups(name, max_count, description, stage, platform, overlay_type):
    """
    Prepares a base template for the json layer file that can be loaded into the MITRE ATT&CK Navigator.
    More information on the version 2.1 layer format:
    https://github.com/mitre/attack-navigator/blob/master/layers/LAYERFORMATv2_1.md
    :param name: name
    :param max_count: the sum of all count values
    :param description: description
    :param stage: stage (act | prepare)
    :param platform: platform
    :param overlay_type: group, visibility or detection
    :return: layer template dictionary
    """
    layer = _get_base_template(name, description, stage, platform, 3)
    layer['gradient'] = {'colors': [COLOR_GRADIENT_MIN, COLOR_GRADIENT_MAX], 'minValue': 0, 'maxValue': max_count}
    layer['legendItems'] = []
    layer['legendItems'].append({'label': 'Tech. not often used', 'color': COLOR_GRADIENT_MIN})
    layer['legendItems'].append({'label': 'Tech. used frequently', 'color': COLOR_GRADIENT_MAX})

    if overlay_type == OVERLAY_TYPE_GROUP:
        layer['legendItems'].append({'label': 'Groups overlay: tech. in group + overlay', 'color': COLOR_GROUP_OVERLAY_MATCH})
        layer['legendItems'].append({'label': 'Groups overlay: tech. in overlay', 'color': COLOR_GROUP_OVERLAY_NO_MATCH})
        layer['legendItems'].append({'label': 'Src. of tech. is only software', 'color': COLOR_SOFTWARE})
        layer['legendItems'].append({'label': 'Src. of tech. is group(s)/overlay + software', 'color': COLOR_GROUP_AND_SOFTWARE})
    elif overlay_type == OVERLAY_TYPE_DETECTION:
        layer['legendItems'].append({'label': 'Tech. in group + detection', 'color': COLOR_GROUP_OVERLAY_MATCH})
        layer['legendItems'].append({'label': 'Tech. in detection', 'color': COLOR_GROUP_OVERLAY_ONLY_DETECTION})
    elif overlay_type == OVERLAY_TYPE_VISIBILITY:
        layer['legendItems'].append({'label': 'Tech. in group + visibility', 'color': COLOR_GROUP_OVERLAY_MATCH})
        layer['legendItems'].append({'label': 'Tech. in visibility', 'color': COLOR_GROUP_OVERLAY_ONLY_VISIBILITY})

    return layer


def get_layer_template_detections(name, description, stage, platform):
    """
    Prepares a base template for the json layer file that can be loaded into the MITRE ATT&CK Navigator.
    More information on the version 2.1 layer format:
    https://github.com/mitre/attack-navigator/blob/master/layers/LAYERFORMATv2_1.md
    :param name: name
    :param description: description
    :param stage: stage (act | prepare)
    :param platform: platform
    :return: layer template dictionary
    """
    layer = _get_base_template(name, description, stage, platform, 0)
    layer['legendItems'] = \
        [
            {'label': 'Detection score 0: Forensics/Context', 'color': COLOR_D_0},
            {'label': 'Detection score 1: Basic', 'color': COLOR_D_1},
            {'label': 'Detection score 2: Fair', 'color': COLOR_D_2},
            {'label': 'Detection score 3: Good', 'color': COLOR_D_3},
            {'label': 'Detection score 4: Very good', 'color': COLOR_D_4},
            {'label': 'Detection score 5: Excellent', 'color': COLOR_D_5}
        ]
    return layer


def get_layer_template_data_sources(name, description, stage, platform):
    """
    Prepares a base template for the json layer file that can be loaded into the MITRE ATT&CK Navigator.
    More information on the version 2.1 layer format:
    https://github.com/mitre/attack-navigator/blob/master/layers/LAYERFORMATv2_1.md
    :param name: name
    :param description: description
    :param stage: stage (act | prepare)
    :param platform: platform
    :return: layer template dictionary
    """
    layer = _get_base_template(name, description, stage, platform, 0)
    layer['legendItems'] = \
        [
            {'label': '1-25% of data sources available', 'color': COLOR_DS_25p},
            {'label': '26-50% of data sources available', 'color': COLOR_DS_50p},
            {'label': '51-75% of data sources available', 'color': COLOR_DS_75p},
            {'label': '76-99% of data sources available', 'color': COLOR_DS_99p},
            {'label': '100% of data sources available', 'color': COLOR_DS_100p}
        ]
    return layer


def get_layer_template_visibility(name, description, stage, platform):
    """
    Prepares a base template for the json layer file that can be loaded into the MITRE ATT&CK Navigator.
    More information on the version 2.1 layer format:
    https://github.com/mitre/attack-navigator/blob/master/layers/LAYERFORMATv2_1.md
    :param name: name
    :param description: description
    :param stage: stage (act | prepare)
    :param platform: platform
    :return: layer template dictionary
    """
    layer = _get_base_template(name, description, stage, platform, 0)
    layer['legendItems'] = \
        [
            {'label': 'Visibility score 1: Minimal', 'color': COLOR_V_1},
            {'label': 'Visibility score 2: Medium', 'color': COLOR_V_2},
            {'label': 'Visibility score 3: Good', 'color': COLOR_V_3},
            {'label': 'Visibility score 4: Excellent', 'color': COLOR_V_4}
        ]
    return layer


def get_layer_template_layered(name, description, stage, platform):
    """
    Prepares a base template for the json layer file that can be loaded into the MITRE ATT&CK Navigator.
    More information on the version 2.1 layer format:
    https://github.com/mitre/attack-navigator/blob/master/layers/LAYERFORMATv2_1.md
    :param name: name
    :param description: description
    :param stage: stage (act | prepare)
    :param platform: platform
    :return: layer template dictionary
    """
    layer = _get_base_template(name, description, stage, platform, 0)
    layer['legendItems'] = \
        [
            {'label': 'Visibility', 'color': COLOR_OVERLAY_VISIBILITY},
            {'label': 'Detection', 'color': COLOR_OVERLAY_DETECTION},
            {'label': 'Visibility and detection', 'color': COLOR_OVERLAY_BOTH}
        ]
    return layer


def write_file(filename_prefix, filename, content):
    """
    Writes content to a file and ensures if the file already exists it won't be overwritten by appending a number
    as suffix.
    :param filename_prefix: prefix part of the filename
    :param filename: filename
    :param content: the content of the file that needs to be written to the file
    :return:
    """
    output_filename = 'output/%s_%s' % (filename_prefix, normalize_name_to_filename(filename))
    output_filename = get_non_existing_filename(output_filename, 'json')

    with open(output_filename, 'w') as f:
        f.write(content)

    print('File written:   ' + output_filename)


def get_non_existing_filename(filename, extension):
    """
    Generates a filename that doesn't exist based on the given filename by appending a number as suffix.
    :param filename:
    :param extension:
    :return:
    """
    if os.path.exists('%s.%s' % (filename, extension)):
        suffix = 1
        while os.path.exists('%s_%s.%s' % (filename, suffix, extension)):
            suffix += 1
        output_filename = '%s_%s.%s' % (filename, suffix, extension)
    else:
        output_filename = '%s.%s' % (filename, extension)
    return output_filename


def backup_file(filename):
    """
    Create a backup of the provided file
    :param filename: existing YAML filename
    :return:
    """
    suffix = 1
    backup_filename = filename.replace('.yaml', '_backup_' + str(suffix) + '.yaml')
    while os.path.exists(backup_filename):
        backup_filename = backup_filename.replace('_backup_' + str(suffix) + '.yaml', '_backup_' + str(suffix+1) + '.yaml')
        suffix += 1

    shutil.copy2(filename, backup_filename)
    print('Written backup file:   ' + backup_filename + '\n')


def get_attack_id(stix_obj):
    """
    Get the Technique, Group or Software ID from the STIX object
    :param stix_obj: STIX object (Technique, Software or Group)
    :return: ATT&CK ID
    """
    for ext_ref in stix_obj['external_references']:
        if ext_ref['source_name'] in ['mitre-attack', 'mitre-mobile-attack', 'mitre-pre-attack']:
            return ext_ref['external_id']


def get_tactics(technique):
    """
    Get all tactics from a given technique
    :param technique: technique STIX object
    :return: list with tactics
    """
    tactics = []
    if 'kill_chain_phases' in technique:
        for phase in technique['kill_chain_phases']:
            tactics.append(phase['phase_name'])

    return tactics


def get_technique(techniques, technique_id):
    """
    Generic function to lookup a specific technique_id in a list of dictionaries with techniques.
    :param techniques: list with all techniques
    :param technique_id: technique_id to look for
    :return: the technique you're searching for. None if not found.
    """
    for tech in techniques:
        if technique_id == get_attack_id(tech):
            return tech
    return None


def ask_yes_no(question):
    """
    Ask the user to a question that needs to be answered with yes or no.
    :param question: The question to be asked
    :return: boolean value indicating a yes (True) or no (False0
    """
    yes_no = ''
    while not re.match('^(y|yes|n|no)$', yes_no, re.IGNORECASE):
        yes_no = input(question + '\n >>   y(yes) / n(no): ')
        print('')

    if re.match('^(y|yes)$', yes_no, re.IGNORECASE):
        return True
    else:
        return False


def ask_multiple_choice(question, list_answers):
    """
    Ask a multiple choice question.
    :param question: the question to ask
    :param list_answers: a list of answer
    :return: the answer
    """
    answer = ''
    answers = ''
    x = 1
    for a in list_answers:
        a = a.replace('\n', '\n     ')
        answers += '  ' + str(x) + ') ' + a + '\n'
        x += 1

    # noinspection Annotator
    while not re.match('(^[1-' + str(len(list_answers)) + ']{1}$)', answer):
        print(question)
        print(answers)
        answer = input(' >>   ')
        print('')

    return list_answers[int(answer)-1]


def fix_date_and_remove_null(yaml_file, date, input_type='ruamel'):
    """
    Remove the single quotes around the date key-value pair in the provided yaml_file and remove any 'null' values
    :param yaml_file: ruamel.yaml instance or location of YAML file
    :param date: string date value (e.g. 2019-01-01)
    :param input_type: input type can be a ruamel.yaml instance or list
    :return: YAML file lines in a list
    """
    _yaml = init_yaml()
    if input_type == 'ruamel':
        # ruamel does not support output to a variable. Therefore we make use of StringIO.
        file = StringIO()
        _yaml.dump(yaml_file, file)
        file.seek(0)
        new_lines = file.readlines()
    elif input_type == 'list':
        new_lines = yaml_file
    elif input_type == 'file':
        new_lines = yaml_file.readlines()

    fixed_lines = [l.replace('\'' + date + '\'', date).replace('null', '')
                   if REGEX_YAML_DATE.match(l) else
                   l.replace('null', '') for l in new_lines]

    return fixed_lines


def get_latest_score_obj(yaml_object):
    """
    Get the the score object in the score_logbook by date
    :param yaml_object: a detection or visibility YAML object
    :return: the latest score object
    """
    if not isinstance(yaml_object['score_logbook'], list):
        yaml_object['score_logbook'] = [yaml_object['score_logbook']]

    if len(yaml_object['score_logbook']) > 0 and 'date' in yaml_object['score_logbook'][0]:
        # for some weird reason 'sorted()' provides inconsistent results
        newest_score_obj = None
        newest_date = None
        for score_obj in yaml_object['score_logbook']:
            if not newest_score_obj or score_obj['date'] > newest_date:
                newest_date = score_obj['date']
                newest_score_obj = score_obj

        return newest_score_obj
    else:
        return None


def get_latest_comment(yaml_object, empty=' '):
    """
    Return the latest comment present in the score_logbook
    :param yaml_object: a detection or visibility YAML object
    :param empty: value for an empty comment
    :return: comment
    """
    score_obj = get_latest_score_obj(yaml_object)
    if score_obj:
        if score_obj['comment'] == '' or not score_obj['comment']:
            return empty
        else:
            return score_obj['comment']
    else:
        return empty


def get_latest_date(yaml_object):
    """
    Return the latest date present in the score_logbook
    :param yaml_object: a detection or visibility YAML object
    :return: date as a datetime object or None
    """
    score_obj = get_latest_score_obj(yaml_object)
    if score_obj:
        return score_obj['date']
    else:
        return None


def get_latest_auto_generated(yaml_object):
    """
    Return the latest auto_generated value present in the score_logbook
    :param yaml_object: a detection or visibility YAML object
    :return: True or False
    """
    score_obj = get_latest_score_obj(yaml_object)
    if score_obj:
        if 'auto_generated' in score_obj:
            return score_obj['auto_generated']
        else:
            return False
    else:
        return False


def get_latest_score(yaml_object):
    """
    Return the latest score present in the score_logbook
    :param yaml_object: a detection or visibility YAML object
    :return: score as an integer or None
    """
    score_obj = get_latest_score_obj(yaml_object)
    if score_obj:
        return score_obj['score']
    else:
        return None


def normalize_name_to_filename(name):
    """
    Normalize the input filename to a lowercase filename and replace spaces with dashes.
    :param name: input filename
    :return: normalized filename
    """
    return name.lower().replace(' ', '-')


def map_techniques_to_data_sources(techniques, my_data_sources):
    """
    This function maps the MITRE ATT&CK techniques to your data sources.
    :param techniques: list with all MITRE ATT&CK techniques
    :param my_data_sources: your configured data sources
    :return: a dictionary containing techniques that can be used in the layer output file.
    """
    my_techniques = {}
    for i_ds in my_data_sources.keys():
        # Loop through all techniques, to find techniques using that data source:
        for t in techniques:
            # If your data source is in the list of data sources for this technique AND if the
            # technique isn't added yet (by an other data source):
            tech_id = get_attack_id(t)
            if 'x_mitre_data_sources' in t:
                if i_ds in t['x_mitre_data_sources'] and tech_id not in my_techniques.keys():
                    my_techniques[tech_id] = {}
                    my_techniques[tech_id]['my_data_sources'] = [i_ds, ]
                    my_techniques[tech_id]['data_sources'] = t['x_mitre_data_sources']
                    # create a list of tactics
                    my_techniques[tech_id]['tactics'] = list(map(lambda k: k['phase_name'], t.get('kill_chain_phases', None)))
                    my_techniques[tech_id]['products'] = set(my_data_sources[i_ds]['products'])
                elif t['x_mitre_data_sources'] and i_ds in t['x_mitre_data_sources'] and tech_id in my_techniques.keys():
                    my_techniques[tech_id]['my_data_sources'].append(i_ds)
                    my_techniques[tech_id]['products'].update(my_data_sources[i_ds]['products'])

    return my_techniques


def get_all_mitre_data_sources():
    """
    Gets all the data sources from the techniques and make a set.
    :return: a sorted list with all data sources
    """
    techniques = load_attack_data(DATA_TYPE_STIX_ALL_TECH)

    data_sources = set()
    for t in techniques:
        if 'x_mitre_data_sources' in t.keys():
            for ds in t['x_mitre_data_sources']:
                data_sources.add(ds)
    return data_sources


def calculate_score(list_detections, zero_value=0):
    """
    Calculates the average score in the given list which may contain multiple detection dictionaries
    :param list_detections: list
    :param zero_value: the value when no scores are there, default 0
    :return: average score
    """
    avg_score = 0
    number = 0
    for v in list_detections:
        score = get_latest_score(v)
        if score >= 0:
            avg_score += score
            number += 1

    avg_score = int(round(avg_score / number, 0) if number > 0 else zero_value)
    return avg_score


def add_entry_to_list_in_dictionary(dictionary, technique_id, key, entry):
    """
    Ensures a list will be created if it doesn't exist in the given dict[technique_id][key] and adds the entry to the
    list. If the dict[technique_id] doesn't exist yet, it will be created.
    :param dictionary: the dictionary
    :param technique_id: the id of the technique in the main dict
    :param key: the key where the list in the dictionary resides
    :param entry: the entry to add to the list
    :return:
    """
    if technique_id not in dictionary.keys():
        dictionary[technique_id] = {}
    if key not in dictionary[technique_id].keys():
        dictionary[technique_id][key] = []
    dictionary[technique_id][key].append(entry)


def load_techniques(file):
    """
    Loads the techniques (including detection and visibility properties).
    :param file: the file location of the YAML file or a dict containing the techniques administration
    :return: dictionary with techniques (incl. properties), name and platform
    """
    my_techniques = {}

    if isinstance(file, dict):
        # file is a dict and created due to the use of an EQL query by the user
        yaml_content = file
    else:
        # file is a file location on disk
        _yaml = init_yaml()
        with open(file, 'r') as yaml_file:
            yaml_content = _yaml.load(yaml_file)

    for d in yaml_content['techniques']:
        # Add detection items:
        if isinstance(d['detection'], dict):  # There is just one detection entry
            add_entry_to_list_in_dictionary(my_techniques, d['technique_id'], 'detection', d['detection'])
        elif isinstance(d['detection'], list):  # There are multiple detection entries
            for de in d['detection']:
                add_entry_to_list_in_dictionary(my_techniques, d['technique_id'], 'detection', de)

        # Add visibility items
        if isinstance(d['visibility'], dict):  # There is just one visibility entry
            add_entry_to_list_in_dictionary(my_techniques, d['technique_id'], 'visibility', d['visibility'])
        elif isinstance(d['visibility'], list):  # There are multiple visibility entries
            for de in d['visibility']:
                add_entry_to_list_in_dictionary(my_techniques, d['technique_id'], 'visibility', de)

        name = yaml_content['name']
        platform = yaml_content['platform']

    return my_techniques, name, platform


def _print_error_msg(msg, print_error):
    if print_error:
        print(msg)
    return True


def _check_health_score_object(yaml_object, object_type, tech_id, health_is_called):
    """
    Check the health of a score_logbook inside  a visibility or detection YAML object
    :param yaml_object: YAML file lines
    :param object_type: 'detection' or 'visibility'
    :param tech_id: ATT&CK technique ID
    :param health_is_called: boolean that specifies if detailed errors in the file will be printed
    :return: True if the YAML file is unhealthy, otherwise False
    """
    has_error = False
    min_score = None
    max_score = None

    if object_type == 'detection':
        min_score = -1
        max_score = 5
    elif object_type == 'visibility':
        min_score = 0
        max_score = 4

    if not isinstance(yaml_object['score_logbook'], list):
        yaml_object['score_logbook'] = [yaml_object['score_logbook']]

    try:
        for score_obj in yaml_object['score_logbook']:
            for key in ['date', 'score', 'comment']:
                if key not in score_obj:
                    has_error = _print_error_msg('[!] Technique ID: ' + tech_id + ' is MISSING a key-value pair in a ' + object_type + ' score object in the \'score_logbook\': ' + key, health_is_called)

            if score_obj['score'] is None:
                has_error = _print_error_msg('[!] Technique ID: ' + tech_id + ' has an EMPTY key-value pair in a ' + object_type + ' score object in the \'score_logbook\': score', health_is_called)

            elif not isinstance(score_obj['score'], int):
                has_error = _print_error_msg('[!] Technique ID: ' + tech_id + ' has an INVALID score format in a ' + object_type + ' score object in the \'score_logbook\': score should be an integer', health_is_called)

            if 'auto_generated' in score_obj:
                if not isinstance(score_obj['auto_generated'], bool):
                    has_error = _print_error_msg(
                        '[!] Technique ID: ' + tech_id + ' has an INVALID auto_generated value in a ' + object_type + ' score object in the \'score_logbook\': auto_generated (if present) should be set to \'true\' or \'false\'', health_is_called)

            if isinstance(score_obj['score'], int):
                if score_obj['date'] is None and score_obj['score'] > -1:
                    has_error = _print_error_msg('[!] Technique ID: ' + tech_id + ' has an EMPTY key-value pair in a ' + object_type + ' score object in the \'score_logbook\': date', health_is_called)

                # noinspection PyChainedComparisons
                if not (score_obj['score'] >= min_score and score_obj['score'] <= max_score):
                    has_error = _print_error_msg(
                        '[!] Technique ID: ' + tech_id + ' has an INVALID ' + object_type + ' score in a score object in the \'score_logbook\': ' + str(score_obj['score']) + ' (should be between ' + str(min_score) + ' and ' + str(max_score) + ')', health_is_called)

                if score_obj['score'] > min_score:
                    try:
                        # noinspection PyStatementEffect
                        score_obj['date'].year
                        # noinspection PyStatementEffect
                        score_obj['date'].month
                        # noinspection PyStatementEffect
                        score_obj['date'].day
                    except AttributeError:
                        has_error = _print_error_msg('[!] Technique ID: ' + tech_id + ' has an INVALID data format in a ' + object_type + ' score object in the \'score_logbook\': date (should be YYYY-MM-DD without quotes)', health_is_called)
    except KeyError:
        pass

    return has_error


def _check_health_yaml_object(yaml_object, object_type, tech_id, health_is_called):
    """
    Check the health of a visibility or detection YAML object
    :param yaml_object: YAML file lines
    :param object_type: 'detection' or 'visibility'
    :param tech_id: ATT&CK technique ID
    :param health_is_called: boolean that specifies if detailed errors in the file will be printed
    :return: True if the YAML file is unhealthy, otherwise False
    """
    has_error = False

    keys = ['applicable_to']

    if object_type == 'detection':
        keys.append('location')

    try:
        for key in keys:
            if not isinstance(yaml_object[key], list):
                has_error = _print_error_msg('[!] Technique ID: ' + tech_id + ' has for the key-value pair \'' + key + '\' in ' + object_type + ' a string value assigned (should be a list)', health_is_called)
            else:
                try:
                    if yaml_object[key][0] is None:
                        has_error = _print_error_msg('[!] Technique ID: ' + tech_id + ' has an EMPTY key-value pair in ' + object_type + ': ' + key, health_is_called)
                except TypeError:
                    has_error = _print_error_msg(
                        '[!] Technique ID: ' + tech_id + ' has an EMPTY key-value pair in ' + object_type + ': ' + key, health_is_called)
    except KeyError:
        pass

    return has_error


def _update_health_state(current, update):
    if current or update:
        return True
    else:
        return update


def _is_file_modified(filename):
    """
    Check if the provided file was modified since the last check
    :param filename: file location
    :return: true when modified else false
    """
    last_modified_file = 'cache/last-modified_' + os.path.basename(filename).rstrip('.yaml')

    def _update_modified_date(date):
        with open(last_modified_file, 'wb') as fd:
            pickle.dump(date, fd)

    if not os.path.exists(last_modified_file):
        last_modified = os.path.getmtime(filename)
        _update_modified_date(last_modified)

        return True
    else:
        with open(last_modified_file, 'rb') as f:
            last_modified_cache = pickle.load(f)
            last_modified_current = os.path.getmtime(filename)

            if last_modified_cache != last_modified_current:
                _update_modified_date(last_modified_current)
                return True
            else:
                return False


def _get_health_state_cache(filename):
    """
    Get file health state from disk
    :param filename: file location
    :return: the cached error state
    """
    last_error_file = 'cache/last-error-state_' + os.path.basename(filename).rstrip('.yaml')

    if os.path.exists(last_error_file):
        with open(last_error_file, 'rb') as f:
            last_error_state_cache = pickle.load(f)

        return last_error_state_cache


def _update_health_state_cache(filename, has_error):
    """
    Write the file health state to disk if changed
    :param filename: file location
    """
    last_error_file = 'cache/last-error-state_' + os.path.basename(filename).rstrip('.yaml')

    def _update(error):
        with open(last_error_file, 'wb') as fd:
            pickle.dump(error, fd)

    if not os.path.exists(last_error_file):
        _update(has_error)
    else:
        error_state_cache = _get_health_state_cache(filename)
        if error_state_cache != has_error:
            _update(has_error)


def check_yaml_file_health(filename, file_type, health_is_called):
    """
    Check on error in the provided YAML file.
    :param filename: YAML file location
    :param file_type: currently only 'FILE_TYPE_TECHNIQUE_ADMINISTRATION' is being supported
    :param health_is_called: boolean that specifies if detailed errors in the file will be printed
    :return:
    """
    # first we check if the file was modified. Otherwise, the health check is skipped for performance reasons
    if _is_file_modified(filename) or health_is_called:
        has_error = False
        if file_type == FILE_TYPE_TECHNIQUE_ADMINISTRATION:
            # check for duplicate tech IDs
            _yaml = init_yaml()
            with open(filename, 'r') as yaml_file:
                yaml_content = _yaml.load(yaml_file)

                tech_ids = list(map(lambda x: x['technique_id'], yaml_content['techniques']))
                tech_dup = []
                for tech in tech_ids:
                    if tech not in tech_dup:
                        tech_dup.append(tech)
                    else:
                        has_error = _print_error_msg('[!] Duplicate technique ID: ' + tech, health_is_called)

                    # check if the technique has a valid format
                    if not REGEX_YAML_TECHNIQUE_ID_FORMAT.match(tech):
                        has_error = _print_error_msg('[!] Invalid technique ID: ' + tech, health_is_called)

            # checks on:
            # - empty key-value pairs: 'applicable_to', 'comment', 'location', 'score_logbook' , 'date', 'score'
            # - invalid date format for: 'date'
            # - detection or visibility score out-of-range
            # - missing key-value pairs: 'applicable_to', 'comment', 'location', 'score_logbook', 'date', 'score'
            # - check on 'applicable_to' values which are very similar

            all_applicable_to = set()
            techniques = load_techniques(filename)
            for tech, v in techniques[0].items():
                for key in ['detection', 'visibility']:
                    if key not in v:
                        has_error = _print_error_msg('[!] Technique ID: ' + tech + ' is MISSING ' + key, health_is_called)
                    elif 'applicable_to' in v:
                        # create at set containing all values for 'applicable_to'
                        all_applicable_to.update([a for v in v[key] for a in v['applicable_to']])

                for detection in v['detection']:
                    for key in ['applicable_to', 'location', 'comment', 'score_logbook']:
                        if key not in detection:
                            has_error = _print_error_msg('[!] Technique ID: ' + tech + ' is MISSING a key-value pair in detection: ' + key, health_is_called)

                    health = _check_health_yaml_object(detection, 'detection', tech, health_is_called)
                    has_error = _update_health_state(has_error, health)
                    health = _check_health_score_object(detection, 'detection', tech, health_is_called)
                    has_error = _update_health_state(has_error, health)

                for visibility in v['visibility']:
                    for key in ['applicable_to', 'comment', 'score_logbook']:
                        if key not in visibility:
                            has_error = _print_error_msg('[!] Technique ID: ' + tech + ' is MISSING a key-value pair in visibility: ' + key, health_is_called)

                    health = _check_health_yaml_object(visibility, 'visibility', tech, health_is_called)
                    has_error = _update_health_state(has_error, health)
                    health = _check_health_score_object(visibility, 'visibility', tech, health_is_called)
                    has_error = _update_health_state(has_error, health)

            # get values within the key-value pair 'applicable_to' which are a very close match
            similar = set()
            for i1 in all_applicable_to:
                for i2 in all_applicable_to:
                    match_value = SequenceMatcher(None, i1, i2).ratio()
                    if match_value > 0.8 and match_value != 1:
                        similar.add(i1)
                        similar.add(i2)

            if len(similar) > 0:
                has_error = _print_error_msg('[!] There are values in the key-value pair \'applicable_to\' which are very similar. Correct where necessary:', health_is_called)
                for s in similar:
                    _print_error_msg('    - ' + s, health_is_called)

            if has_error and not health_is_called:
                print(HEALTH_HAS_ERROR + filename)
            elif has_error and health_is_called:
                print('    - ' + filename)

            _update_health_state_cache(filename, has_error)
    elif _get_health_state_cache(filename):
        print(HEALTH_HAS_ERROR + filename)


def _check_file_type(filename, file_type=None):
    """
    Check if the provided YAML file has the key 'file_type' and possible if that key matches a specific value.
    :param filename: path to a YAML file
    :param file_type: value to check against the 'file_type' key in the YAML file
    :return: the file_type if present, else None is returned
    """
    if not os.path.exists(filename):
        print('[!] File: \'' + filename + '\' does not exist')
        return None

    _yaml = init_yaml()
    with open(filename, 'r') as yaml_file:
        try:
            yaml_content = _yaml.load(yaml_file)
        except Exception as e:
            print('[!] File: \'' + filename + '\' is not a valid YAML file.')
            print('  ' + str(e))  # print more detailed error information to help the user in fixing the error.
            return None

        # This check is performed because a text file will also be considered to be valid YAML. But, we are using
        # key-value pairs within the YAML files.
        if not hasattr(yaml_content, 'keys'):
            print('[!] File: \'' + filename + '\' is not a valid YAML file.')
            return None

        if 'file_type' not in yaml_content.keys():
            print('[!] File: \'' + filename + '\' does not contain a file_type key.')
            return None
        elif file_type:
            if file_type != yaml_content['file_type']:
                print('[!] File: \'' + filename + '\' is not a file type of: \'' + file_type + '\'')
                return None
            else:
                return yaml_content
        else:
            return yaml_content


def check_file(filename, file_type=None, health_is_called=False):
    """
    Calls three functions to perform the following checks: is the file a valid YAML file, needs the file to be upgrade,
    does the file contain errors.
    :param filename: path to a YAML file
    :param file_type: value to check against the 'file_type' key in the YAML file
    :param health_is_called: boolean that specifies if detailed errors in the file will be printed by the function 'check_yaml_file_health'
    :return: the file_type if present, else None is returned
    """

    yaml_content = _check_file_type(filename, file_type)

    # if the file is a valid YAML, continue. Else, return None
    if yaml_content:
        upgrade_yaml_file(filename, file_type, yaml_content['version'], load_attack_data(DATA_TYPE_STIX_ALL_TECH))
        check_yaml_file_health(filename, file_type, health_is_called)

        return yaml_content['file_type']

    return yaml_content  # value is None


def get_updates(update_type, sort='modified'):
    """
    Print a list of updates for a techniques, groups or software. Sort by modified or creation date.
    :param update_type: the type of update: techniques, groups or software
    :param sort: sort the list by modified or creation date
    :return:
    """
    if update_type[:-1] == 'technique':
        techniques = load_attack_data(DATA_TYPE_STIX_ALL_TECH)
        sorted_techniques = sorted(techniques, key=lambda k: k[sort])

        for t in sorted_techniques:
            print(get_attack_id(t) + ' ' + t['name'])
            print(' ' * 6 + 'created:  ' + t['created'].strftime('%Y-%m-%d'))
            print(' ' * 6 + 'modified: ' + t['modified'].strftime('%Y-%m-%d'))
            print(' ' * 6 + 'matrix:   ' + t['external_references'][0]['source_name'][6:])
            tactics = get_tactics(t)
            if tactics:
                print(' ' * 6 + 'tactic:   ' + ', '.join(tactics))
            else:
                print(' ' * 6 + 'tactic:   None')
            print('')

    elif update_type[:-1] == 'group':
        groups = load_attack_data(DATA_TYPE_STIX_ALL_GROUPS)
        sorted_groups = sorted(groups, key=lambda k: k[sort])

        for g in sorted_groups:
            print(get_attack_id(g) + ' ' + g['name'])
            print(' ' * 6 + 'created:  ' + g['created'].strftime('%Y-%m-%d'))
            print(' ' * 6 + 'modified: ' + g['modified'].strftime('%Y-%m-%d'))
            print('')

    elif update_type == 'software':
        software = load_attack_data(DATA_TYPE_STIX_ALL_SOFTWARE)
        sorted_software = sorted(software, key=lambda k: k[sort])

        for s in sorted_software:
            print(get_attack_id(s) + ' ' + s['name'])
            print(' ' * 6 + 'created:  ' + s['created'].strftime('%Y-%m-%d'))
            print(' ' * 6 + 'modified: ' + s['modified'].strftime('%Y-%m-%d'))
            print(' ' * 6 + 'matrix:   ' + s['external_references'][0]['source_name'][6:])
            print(' ' * 6 + 'type:     ' + s['type'])
            if 'x_mitre_platforms' in s:
                print(' ' * 6 + 'platform: ' + ', '.join(s['x_mitre_platforms']))
            else:
                print(' ' * 6 + 'platform: None')
            print('')


def get_statistics_mitigations(matrix):
    """
    Print out statistics related to mitigations and how many techniques they cover
    :return:
    """

    if matrix == 'enterprise':
        mitigations = load_attack_data(DATA_TYPE_STIX_ALL_ENTERPRISE_MITIGATIONS)
    elif matrix == 'mobile':
        mitigations = load_attack_data(DATA_TYPE_STIX_ALL_MOBILE_MITIGATIONS)

    mitigations_dict = dict()
    for m in mitigations:
        if m['external_references'][0]['external_id'].startswith('M'):
            mitigations_dict[m['id']] = {'mID': m['external_references'][0]['external_id'], 'name': m['name']}

    relationships = load_attack_data(DATA_TYPE_STIX_ALL_RELATIONSHIPS)
    relationships_mitigates = [r for r in relationships
                               if r['relationship_type'] == 'mitigates'
                               if r['source_ref'].startswith('course-of-action')
                               if r['target_ref'].startswith('attack-pattern')
                               if r['source_ref'] in mitigations_dict]

    # {id: {name: ..., count: ..., name: ...} }
    count_dict = dict()
    for r in relationships_mitigates:
        src_ref = r['source_ref']

        m = mitigations_dict[src_ref]
        if m['mID'] not in count_dict:
            count_dict[m['mID']] = dict()
            count_dict[m['mID']]['count'] = 1
            count_dict[m['mID']]['name'] = m['name']
        else:
            count_dict[m['mID']]['count'] += 1

    count_dict_sorted = dict(sorted(count_dict.items(), key=lambda kv: kv[1]['count'], reverse=True))

    str_format = '{:<6s} {:<14s} {:s}'
    print(str_format.format('Count', 'Mitigation ID', 'Name'))
    print('-' * 60)
    for k, v in count_dict_sorted.items():
        print(str_format.format(str(v['count']), k, v['name']))


def get_statistics_data_sources():
    """
    Print out statistics related to data sources and how many techniques they cover.
    :return:
    """
    techniques = load_attack_data(DATA_TYPE_STIX_ALL_TECH)

    # {data_source: {techniques: [T0001, ...}, count: ...}
    data_sources_dict = {}
    for tech in techniques:
        tech_id = get_attack_id(tech)
        # Not every technique has a data source listed
        data_sources = tech.get('x_mitre_data_sources', None)
        if data_sources:
            for ds in data_sources:
                if ds not in data_sources_dict:
                    data_sources_dict[ds] = {'techniques': [tech_id], 'count': 1}
                else:
                    data_sources_dict[ds]['techniques'].append(tech_id)
                    data_sources_dict[ds]['count'] += 1

    # sort the dict on the value of 'count'
    data_sources_dict_sorted = dict(sorted(data_sources_dict.items(), key=lambda kv: kv[1]['count'], reverse=True))
    str_format = '{:<6s} {:s}'
    print(str_format.format('Count', 'Data Source'))
    print('-'*50)
    for k, v in data_sources_dict_sorted.items():
        print(str_format.format(str(v['count']), k))
