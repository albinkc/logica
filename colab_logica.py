#!/usr/bin/python
#
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Library for using Logica in CoLab."""

from .common import color
from .common import concertina_lib

from .compiler import rule_translate
from .compiler import universe

import IPython

from IPython.core.magic import register_cell_magic
from IPython.display import display

import os

import pandas

from .parser_py import parse

from google.cloud import bigquery
from google.colab import auth
from google.colab import widgets


PROJECT = None

DB_CONNECTION = None

USER_AUTHENTICATED = False

TABULATED_OUTPUT = True

def SetProject(project):
  global PROJECT
  PROJECT = project

def SetDbConnection(connection):
  global DB_CONNECTION
  DB_CONNECTION = connection

def EnsureAuthenticatedUser():
  global USER_AUTHENTICATED
  global PROJECT
  if USER_AUTHENTICATED:
    return
  auth.authenticate_user()
  if PROJECT is None:
    print("Please enter project_id to use for BigQuery querries.")
    PROJECT = input()
    print("project_id is set to %s" % PROJECT)
    print("You can change it with logica.colab_logica.SetProject command.")
  USER_AUTHENTICATED = True

def SetTabulatedOutput(tabulated_output):
  global TABULATED_OUTPUT
  TABULATED_OUTPUT = tabulated_output

def TabBar(*args):
  """Returns a real TabBar or a mock. Useful for UIs that don't support JS."""
  if TABULATED_OUTPUT:
    return widgets.TabBar(*args)
  class MockTab:
      def __init__(self):
          pass
      def __enter__(self):
          pass
      def __exit__(self, *x):
          pass
  class MockTabBar:
      def __init__(self):
          pass
      def output_to(self, x):
          return MockTab()
  return MockTabBar()

@register_cell_magic
def logica(line, cell):
  Logica(line, cell, run_query=True)


def ParseList(line):
  line = line.strip()
  if not line:
    predicates = []
  else:
    predicates = [p.strip() for p in line.split(',')]
  return predicates


def RunSQL(sql, engine):
  if engine == 'bigquery':
    EnsureAuthenticatedUser()
    client = bigquery.Client(project=PROJECT)
    return client.query(sql).to_dataframe()
  elif engine == 'psql':
    return pandas.read_sql(sql, DB_CONNECTION)
  elif engine == 'sqlite':
    statements = parse.SplitRaw(sql, ';')
    for s in statements[:-2]:
      cursor = DB_CONNECTION.execute(s)
    return pandas.read_sql(statements[-2], DB_CONNECTION)
  else:
    raise Exception('Logica only supports BigQuery, PostgreSQL and SQLite '
                    'for now.')


def Logica(line, cell, run_query):
  """Running Logica predicates and storing results."""
  predicates = ParseList(line)
  try:
    parsed_rules = parse.ParseFile(cell)['rule']
  except parse.ParsingException as e:
    e.ShowMessage()
    return
  program = universe.LogicaProgram(parsed_rules)
  engine = program.annotations.Engine()

  bar = TabBar(predicates + ['(Log)'])
  logs_idx = len(predicates)

  executions = []
  ip = IPython.get_ipython()
  for idx, predicate in enumerate(predicates):
    with bar.output_to(logs_idx):
      print('Running %s' % predicate)
      try:
        sql = program.FormattedPredicateSql(predicate)
        executions.append(program.execution)
        ip.push({predicate + '_sql': sql})
      except rule_translate.RuleCompileException as e:
        e.ShowMessage()
        return

    # Publish output to Colab cell.
    with bar.output_to(idx):
      sub_bar = TabBar(['SQL', 'Result'])
      with sub_bar.output_to(0):
        print(
            color.Format(
                'The following query is stored at {warning}%s{end} '
                'variable.' % (
                    predicate + '_sql')))
        print(sql)

    # with bar.output_to(logs_idx):
    #   if run_query:
    #     t = RunSQL(sql, engine)
    #    ip.push({predicate: t})
    result_map = concertina_lib.ExecuteLogicaProgram(executions)
 
    for idx, predicate in enumerate(predicates):
      t = result_map[predicate]
      ip.push({predicate: t})
      with bar.output_to(idx):
        with sub_bar.output_to(1):
          if run_query:
            print(
                color.Format(
                    'The following table is stored at {warning}%s{end} '
                    'variable.' %
                    predicate))
            display(t)
          else:
            print('The query was not run.')

def PostgresJumpStart():
  # Install postgresql server.
  print("Installing and configuring an empty PostgreSQL database.")
  result = 0
  result += os.system('sudo apt-get -y -qq update')
  result += os.system('sudo apt-get -y -qq install postgresql')
  result += os.system('sudo service postgresql start')
  result += os.system(
    'sudo -u postgres psql -c "CREATE USER logica WITH SUPERUSER"')
  result += os.system(
    'sudo -u postgres psql -c "ALTER USER logica PASSWORD \'logica\';"')
  result += os.system(
    'sudo -u postgres psql -U postgres -c \'CREATE DATABASE logica;\'')
  if result != 0:
    print("""Installation failed. Please try the following manually:
# Install Logica.
!pip install logica

# Install postgresql server.
!sudo apt-get -y -qq update
!sudo apt-get -y -qq install postgresql
!sudo service postgresql start

# Prepare database for Logica.
!sudo -u postgres psql -c "CREATE USER logica WITH SUPERUSER"
!sudo -u postgres psql -c "ALTER USER logica PASSWORD 'logica';"
!sudo -u postgres psql -U postgres -c 'CREATE DATABASE logica;'

# Connect to the database.
from logica import colab_logica
from sqlalchemy import create_engine
import pandas
engine = create_engine('postgresql+psycopg2://logica:logica@127.0.0.1', pool_recycle=3600);
connection = engine.connect();
colab_logica.SetDbConnection(connection)""")
    return
  print('Installation succeeded. Connecting...')
  # Connect to the database.
  from logica import colab_logica
  from sqlalchemy import create_engine
  import pandas
  engine = create_engine('postgresql+psycopg2://logica:logica@127.0.0.1', pool_recycle=3600)
  connection = engine.connect()
  SetDbConnection(connection)
  print('Connected.')
