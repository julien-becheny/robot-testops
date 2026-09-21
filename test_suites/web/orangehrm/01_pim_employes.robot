*** Settings ***
Documentation       Gestion des employés (module PIM).
...
...                 Traduction de la fiche de recette REC-PIM-001 « Création d'un nouvel
...                 employé ». Deux points de la fiche ont dû être précisés pour qu'elle
...                 devienne exécutable :
...                 - « l'employé est créé » n'est pas vérifiable : l'assertion porte sur le
...                 fait qu'il ressorte d'une recherche, pas sur le message de confirmation,
...                 qui s'efface au bout de quelques secondes ;
...                 - « nom au choix du testeur » : la base de démonstration est partagée,
...                 le matricule est donc généré à chaque run et supprimé en teardown.

Resource  ../../../libraries/resources/web/orangehrm/kw_orangehrm.resource
Variables  ../../../libraries/test_data/web/orangehrm/td_orangehrm.yml

Test Teardown  Clean Up Created Employee  ${CREATED_EMPLOYEE_ID}

Test Tags  orangehrm  pim  web  regression


*** Variables ***
# Repli lu par le teardown quand le test échoue avant d'avoir créé quoi que ce soit.
${CREATED_EMPLOYEE_ID}  ${EMPTY}


*** Test Cases ***
PIM - Create Employee
  [Documentation]  Crée un employé et vérifie qu'il est bien enregistré côté serveur.
  [Tags]  feat:orangehrm.pim.creation_employe
  ${Employee_Id}=  New Employee Id
  VAR  ${CREATED_EMPLOYEE_ID}  ${Employee_Id}  scope=TEST
  Open And Login As  ADMIN
  Open Employee List
  Open Add Employee Form
  Create Employee
  ...  ${TD_ORANGEHRM}[EMPLOYEE][FIRST_NAME]
  ...  ${TD_ORANGEHRM}[EMPLOYEE][LAST_NAME]
  ...  ${Employee_Id}
  Employee Details Should Show
  ...  ${TD_ORANGEHRM}[EMPLOYEE][FIRST_NAME]
  ...  ${TD_ORANGEHRM}[EMPLOYEE][LAST_NAME]
  Open Employee List
  ${Found}=  Search Employee By Id  ${Employee_Id}
  Employee Should Be Listed Once
  ...  ${Found}
  ...  ${Employee_Id}
  ...  ${TD_ORANGEHRM}[EMPLOYEE][FIRST_NAME]
  ...  ${TD_ORANGEHRM}[EMPLOYEE][LAST_NAME]
