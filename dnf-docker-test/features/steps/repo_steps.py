from __future__ import absolute_import
from __future__ import unicode_literals

import glob
import os
import tempfile

from behave import given
from behave import register_type
from behave import when
from behave.model import Table
import jinja2
import parse
from whichcraft import which

from command_steps import step_i_successfully_run_command
from file_steps import HEADINGS_INI
from file_steps import conf2table
from file_steps import step_a_file_filepath_with
from file_steps import step_an_ini_file_filepath_with
import file_utils
import table_utils
import repo_utils

PKG_TMPL = """
Name:           {{ name }}
Summary:        {{ summary|default("Empty") }}
Version:        {{ version|default("1") }}
Release:        {{ release|default("1") }}%{?dist}

License:        {{ license|default("Public Domain") }}

{%- if arch is not defined or arch == "noarch" %}
BuildArch:      noarch
{%- endif %}

{%- if buildrequires is defined %}
{% for buildreq in buildrequires %}
BuildRequires:  {{ buildreq }}
{%- endfor %}
{%- endif %}

{%- if requires is defined %}
{% for req in requires %}
Requires:       {{ req }}
{%- endfor %}
{%- endif %}

{%- if obsoletes is defined %}
{% for obs in obsoletes %}
Obsoletes:      {{ obs }}
{%- endfor %}
{%- endif %}

{%- if conflicts is defined %}
{% for con in conflicts %}
Conflicts:       {{ con }}
{%- endfor %}
{%- endif %}

{%- if provides is defined %}
{% for prv in provides %}
Provides:       {{ prv }}
{%- endfor %}
{%- endif %}

%description
%{summary}.

%files
"""
REPO_TMPL = "/etc/yum.repos.d/{!s}.repo"
HEADINGS_REPO = ["Package", "Tag", "Value"]
PKG_TAGS_REPEATING = ["BuildRequires", "Requires", "Obsoletes", "Provides", "Conflicts"]
PKG_TAGS = ["Summary", "Version", "Release", "License", "Arch"] + PKG_TAGS_REPEATING

JINJA_ENV = jinja2.Environment(undefined=jinja2.StrictUndefined)

@parse.with_pattern(r"enable|disable")
def parse_enable_disable(text):
    if text == "enable":
        return True
    if text == "disable":
        return False
    assert False

register_type(enable_disable=parse_enable_disable)

@parse.with_pattern(r"local |http |ftp |")
def parse_repo_type(text):
    if text == "http ":
        return "http"
    elif text == "ftp ":
        return "ftp"
    elif text == 'local ' or text == '':
        return "file"
    assert False

register_type(repo_type=parse_repo_type)

@when('I remove all repositories')
def step_i_remove_all_repositories(ctx):
    """
    Remove all ``*.repo`` files in ``/etc/yum.repos.d/``.
    """
    for f in glob.glob("/etc/yum.repos.d/*.repo"):
        os.remove(f)

@given('{rtype:repo_type}repository "{repository}" with packages')
def given_repository_with_packages(ctx, rtype, repository):
    """
    Builds dummy packages, creates repo and *.repo* file.
    Supported repo types are http, ftp or local (default).
    Supported architectures are x86_64, i686 and noarch (default).

    .. note::

       Requires *rpmbuild* and *createrepo_c*.

    Requires table with following headers:

    ========= ===== =======
     Package   Tag   Value
    ========= ===== =======

    *Tag* is tag in RPM. Supported ones are:

    ============= ===============
         Tag       Default value 
    ============= ===============
    Summary       Empty          
    Version       1              
    Release       1              
    Arch          x86_64         
    License       Public Domain  
    BuildRequires []             
    Requires      []             
    Obsoletes     []             
    Provides      []             
    Conflicts     []             
    ============= ===============

    All packages are built during step execution.

    .. note::

        *BuildRequires* are ignored for build-time (*rpmbuild* is executed
        with ``--nodeps`` option).

    Examples:

    .. code-block:: gherkin

       Feature: Working with repositories

         Background: Repository base with dummy package
               Given http repository base with packages
                  | Package | Tag | Value |
                  | foo     |     |       |

         Scenario: Installing dummy package from background
              When I enable repository base
              Then I successfully run "dnf -y install foo"
    """
    packages = table_utils.parse_skv_table(ctx, HEADINGS_REPO,
                                           PKG_TAGS, PKG_TAGS_REPEATING)

    rpmbuild = which("rpmbuild")
    ctx.assertion.assertIsNotNone(rpmbuild, "rpmbuild is required")
    createrepo = which("createrepo_c")
    ctx.assertion.assertIsNotNone(createrepo, "createrepo_c is required")

    if rtype == 'http':
        tmpdir = tempfile.mkdtemp(dir='/var/www/html')
        repopath = os.path.join('localhost', os.path.basename(tmpdir))
    elif rtype == 'ftp':
        tmpdir = tempfile.mkdtemp(dir='/var/ftp/pub')
        repopath = os.path.join('localhost/pub', os.path.basename(tmpdir))
    else:
        tmpdir = tempfile.mkdtemp()
        repopath = tmpdir
    template = JINJA_ENV.from_string(PKG_TMPL)
    for name, settings in packages.items():
        settings = {k.lower(): v for k, v in settings.items()}
        ctx.text = template.render(name=name, **settings)
        fname = "{!s}/{!s}.spec".format(tmpdir, name)
        step_a_file_filepath_with(ctx, fname)
        if 'arch' not in settings or settings['arch'] == 'noarch':
            cmd = "{!s} --define '_rpmdir {!s}' -bb {!s}".format(
                rpmbuild, tmpdir, fname)
        else:
            cmd = "setarch {!s} {!s} --define '_rpmdir {!s}' --target {!s} -bb {!s}".format(
                settings['arch'], rpmbuild, tmpdir, settings['arch'], fname)
        step_i_successfully_run_command(ctx, cmd)

    cmd = "{!s} {!s}".format(createrepo, tmpdir)
    step_i_successfully_run_command(ctx, cmd)

    # set proper directory content ownership
    file_utils.set_dir_content_ownership(ctx, tmpdir)

    repofile = REPO_TMPL.format(repository)
    ctx.table = Table(HEADINGS_INI)
    ctx.table.add_row([repository, "name",     repository])
    ctx.table.add_row(["",         "enabled",  "False"])
    ctx.table.add_row(["",         "gpgcheck", "False"])
    ctx.table.add_row(["",         "baseurl",  "{!s}://{!s}".format(rtype, repopath)])
    step_an_ini_file_filepath_with(ctx, repofile)

@given('empty repository "{repository}"')
def given_empty_repository(ctx, repository):
    """
    Same as :ref:`Given repository "{repository}" with packages`, but without
    packages (empty).
    """
    ctx.table = Table(HEADINGS_REPO)
    given_repository_with_packages(ctx, "file", repository)

@when('I {state:enable_disable} repository "{repository}"')
def i_enable_disable_repository(ctx, state, repository):
    """
    Enable/Disable repository with given name.
    """
    repofile = REPO_TMPL.format(repository)
    conf = file_utils.read_ini_file(repofile)
    conf.set(repository, "enabled", str(state))
    ctx.table = conf2table(conf)
    step_an_ini_file_filepath_with(ctx, repofile)

@given('updateinfo defined in repository "{repository}"')
def step_updateinfo_defined_in_repository(ctx, repository):
    """
    For a given repository creates updateinfo.xml file with described
    updates and recreates the repo

    .. note::

       Requires *modifyrepo_c* and the repo to be already created.

    Requires table with following headers:

    ==== ===== =======
     Id   Tag   Value
    ==== ===== =======

    *Tag* is describing attributes of the respective update.
    Supported tags are:

    ============ =========================
         Tag      Default value
    ============ =========================
    Title        Default title of Id
    Type         security
    Description  Default description of Id
    Summary      Default summary of Id
    Severity     Low
    Solution     Default solution of Id
    Rights       nobody
    Issued       2017-01-01 00:00:01
    Updated      2017-01-01 00:00:01
    Reference    none
    Package      none
    ============ =========================

    Examples:

    .. code-block:: gherkin

       Feature: Defining updateinfo in a repository

         @setup
         Scenario: Repository base with updateinfo defined
              Given repository "base" with packages
                 | Package | Tag     | Value |
                 | foo     | Version | 2     |
                 | bar     | Version | 2     |
              And updateinfo defined in repository "base"
                 | Id            | Tag         | Value                     |
                 | RHSA-2017-001 | Title       | foo bar security update   |
                 |               | Type        | security                  |
                 |               | Description | Fixes buffer overflow     |
                 |               | Summary     | Critical bug is fixed     |
                 |               | Severity    | Critical                  |
                 |               | Solution    | Update to the new version |
                 |               | Rights      | Copyright 2017 Baz Inc    |
                 |               | Reference   | CVE-2017-0001             |
                 |               | Reference   | BZ123456                  |
                 |               | Package     | foo-2                     |
                 |               | Package     | bar-2                     |

    .. note::

       Specifying Version or Release in Package tag is not necessary, however
       when multiple RPMs matches the string the last one from the sorted
       list is used.
    """
    HEADINGS_GROUP = ['Id', 'Tag', 'Value']
    UPDATEINFO_TAGS_REPEATING = ['Package', 'Reference']
    UPDATEINFO_TAGS = ['Title', 'Type', 'Description', 'Solution', 'Summary', 'Severity', 'Rights', 'Issued', 'Updated'] + \
                      UPDATEINFO_TAGS_REPEATING
    updateinfo_table = table_utils.parse_skv_table(ctx, HEADINGS_GROUP, UPDATEINFO_TAGS, UPDATEINFO_TAGS_REPEATING)

    # verify that modifyrepo_c is present
    modifyrepo = which("modifyrepo_c")
    ctx.assertion.assertIsNotNone(modifyrepo, "modifyrepo_c is required")

    # prepare updateinfo.xml content
    repodir = repo_utils.get_repo_dir(repository)
    updateinfo_xml = repo_utils.get_updateinfo_xml(repository, updateinfo_table)

    # save it to the updateinfo.xml file and recreate the repodata
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "updateinfo.xml"), 'w') as fw:
        fw.write(updateinfo_xml)
    file_utils.set_dir_content_ownership(ctx, repodir, 'root')   # change file ownership to root so we can change it
    cmd = "{!s} {!s} {!s}".format(modifyrepo, os.path.join(tmpdir, 'updateinfo.xml'), os.path.join(repodir, 'repodata'))
    step_i_successfully_run_command(ctx, cmd)
    file_utils.set_dir_content_ownership(ctx, repodir)   # restore file ownership
