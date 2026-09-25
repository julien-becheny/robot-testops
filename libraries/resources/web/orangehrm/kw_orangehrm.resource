*** Settings ***
Documentation       Keywords métier du module OrangeHRM (progiciel RH de démonstration).
...                 Règle POM : to_* = locators seuls, kw_* = actions métier, td_* = données.
...
...                 La base de démonstration est PARTAGÉE et n'est jamais réinitialisée :
...                 chaque test crée ses données sous un identifiant unique et les supprime
...                 en teardown. Sans cela, le deuxième run travaille sur les restes du premier.

Library  DateTime
Library  String
Resource  ../../common/kw_browser.resource
Variables  ../../../test_objects/web/orangehrm/to_login.yml
Variables  ../../../test_objects/web/orangehrm/to_navigation.yml
Variables  ../../../test_objects/web/orangehrm/to_employee_list.yml
Variables  ../../../test_objects/web/orangehrm/to_add_employee.yml
Variables  ../../../test_objects/web/orangehrm/to_personal_details.yml
Variables  ../../../test_objects/web/orangehrm/to_dialog.yml


*** Keywords ***
New Employee Id
  [Documentation]  Fabrique un matricule unique au run.
  ...  C'est lui, et non le nom, qui sert de clé de recherche : le champ « Employee Id »
  ...  est une saisie libre, là où « Employee Name » est une autocomplétion asynchrone.
  ...  L'application refuse au-delà de 10 caractères : 2 + 6 + 2 tient dans la limite.
  ${Time}=  Get Current Date  result_format=%H%M%S
  ${Random}=  Generate Random String  2  [NUMBERS]
  RETURN  TO${Time}${Random}

Open OrangeHRM
  [Documentation]  Ouvre le navigateur sur la page de connexion.
  Open Module  orangehrm
  Wait For Screen  orangehrm.connexion  ${TO_LOGIN}[BTN_LOGIN]

Login As
  [Documentation]  Renseigne le formulaire de connexion avec le profil donné.
  [Arguments]  ${Profile}=ADMIN
  ${Account}=  Get Account  ${Profile}  ${ENVIRONMENT}
  Fill Text  ${TO_LOGIN}[FLD_USERNAME]  ${Account}[username]
  Fill Secret  ${TO_LOGIN}[FLD_PASSWORD]  ${Account}[password]
  Click  ${TO_LOGIN}[BTN_LOGIN]

Open And Login As
  [Documentation]  Raccourci : ouvre le navigateur puis se connecte.
  [Arguments]  ${Profile}=ADMIN
  Open OrangeHRM
  Login As  ${Profile}
  Wait For Screen  orangehrm.tableau_de_bord  ${TO_NAVIGATION}[LNK_MENU_PIM]

Log In Once For The Suite
  [Documentation]  `Suite Setup` : joue le formulaire de connexion UNE fois, garde la session.
  ...  Les tests ouvrent ensuite un contexte déjà connecté (cf. `Open OrangeHRM Session`).
  ...  C'est aussi le seul endroit du module où le chemin de connexion réel est exercé :
  ...  s'il casse, la suite entière ne démarre pas, et le rapport le dit une fois au lieu
  ...  d'afficher N échecs qui racontent tous le même incident.
  [Arguments]  ${Profile}=ADMIN
  Open And Login As  ${Profile}
  Remember Login State
  Close Browser

Open OrangeHRM Session
  [Documentation]  Ouvre le navigateur sur la session enregistrée par le `Suite Setup`.
  ...  L'application redirige la page de connexion vers le tableau de bord tant que le
  ...  cookie est valide : une session périmée échoue donc ici, et non trois écrans plus
  ...  loin sur un bouton « introuvable ».
  Should Not Be Empty  ${AUTH_STATE}
  ...  msg=Aucune session enregistrée : lancer le DOSSIER test_suites/web/orangehrm (son __init__.robot fait la connexion), pas le fichier de test seul.
  Open Module  orangehrm
  Wait For Screen  orangehrm.tableau_de_bord  ${TO_NAVIGATION}[LNK_MENU_PIM]

Open Employee List
  [Documentation]  Ouvre la liste des employés depuis le menu latéral.
  Click  ${TO_NAVIGATION}[LNK_MENU_PIM]
  Wait For Screen  orangehrm.pim.liste_employes  ${TO_EMPLOYEE_LIST}[BTN_ADD]

Open Add Employee Form
  [Documentation]  Ouvre le formulaire de création depuis la liste des employés.
  Click  ${TO_EMPLOYEE_LIST}[BTN_ADD]
  Wait For Screen  orangehrm.pim.creation_employe  ${TO_ADD_EMPLOYEE}[FLD_FIRST_NAME]

Create Employee
  [Documentation]  Renseigne le formulaire de création et enregistre.
  ...  Le matricule proposé par l'application est écrasé par celui du test.
  ...  La fiche s'affiche avant ses données : ses champs se remplissent à la réponse de
  ...  `personal-details`. L'attente porte sur cette réponse, sans quoi la vérification
  ...  suivante lit un formulaire encore vide.
  [Arguments]  ${First_Name}  ${Last_Name}  ${Employee_Id}
  Fill Text  ${TO_ADD_EMPLOYEE}[FLD_FIRST_NAME]  ${First_Name}
  Fill Text  ${TO_ADD_EMPLOYEE}[FLD_LAST_NAME]  ${Last_Name}
  Fill Text  ${TO_ADD_EMPLOYEE}[FLD_EMPLOYEE_ID]  ${Employee_Id}
  ${Details}=  Promise To  Wait For Response
  ...  matcher=**/api/v2/pim/employees/*/personal-details
  ...  timeout=20s
  Click  ${TO_ADD_EMPLOYEE}[BTN_SAVE]
  Wait For  ${Details}
  Wait For Screen  orangehrm.pim.details_employe  ${TO_PERSONAL_DETAILS}[LBL_TITLE]

Employee Details Should Show
  [Documentation]  Vérifie que la fiche de l'employé affiche bien l'identité saisie.
  [Arguments]  ${First_Name}  ${Last_Name}
  Get Property  ${TO_PERSONAL_DETAILS}[FLD_FIRST_NAME]  value  ==  ${First_Name}
  Get Property  ${TO_PERSONAL_DETAILS}[FLD_LAST_NAME]  value  ==  ${Last_Name}

Search Employee By Id
  [Documentation]  Filtre la liste des employés sur un matricule et renvoie le nombre
  ...  d'employés trouvés, tel que le serveur l'a compté.
  ...  L'attente porte sur la réponse HTTP, pas sur l'écran : le tableau affiché reste
  ...  celui de la recherche précédente jusqu'à ce que la réponse arrive et soit rendue.
  [Arguments]  ${Employee_Id}
  Fill Text  ${TO_EMPLOYEE_LIST}[FLD_EMPLOYEE_ID]  ${Employee_Id}
  ${Search}=  Promise To  Wait For Response
  ...  matcher=**/api/v2/pim/employees?**employeeId=${Employee_Id}**
  ...  timeout=20s
  Click  ${TO_EMPLOYEE_LIST}[BTN_SEARCH]
  ${Response}=  Wait For  ${Search}
  RETURN  ${Response}[body][meta][total]

Employee Should Be Listed Once
  [Documentation]  Vérifie que le matricule ne ramène qu'un employé, et que c'est le bon.
  ...  Le serveur fait foi ; l'écran doit ensuite le refléter.
  [Arguments]  ${Found}  ${Employee_Id}  ${First_Name}  ${Last_Name}
  Should Be Equal As Integers  ${Found}  1
  Get Element Count  ${TO_EMPLOYEE_LIST}[ROW_ANY]  ==  1
  ${Row_Selector}=  Format String  ${TO_EMPLOYEE_LIST}[ROW_BY_ID]  id=${Employee_Id}
  ${Row}=  Get Text  ${Row_Selector}
  Should Contain  ${Row}  ${First_Name}
  Should Contain  ${Row}  ${Last_Name}

Employee Should Not Exist
  [Documentation]  Vérifie qu'aucun employé ne porte ce matricule.
  [Arguments]  ${Employee_Id}
  ${Found}=  Search Employee By Id  ${Employee_Id}
  Should Be Equal As Integers  ${Found}  0

Delete Employee If Present
  [Documentation]  Supprime l'employé portant ce matricule, s'il existe, et vérifie qu'il a disparu.
  ...  Un test interrompu avant la création n'a rien laissé : le nettoyage doit alors se taire.
  ...  La popup se ferme dès le clic, avant la réponse du serveur : la recherche de contrôle
  ...  attend donc la fin de la suppression, sans quoi elle trouve encore l'employé.
  [Arguments]  ${Employee_Id}
  Open Employee List
  ${Found}=  Search Employee By Id  ${Employee_Id}
  IF  ${Found} == 0  RETURN
  Get Element Count  ${TO_EMPLOYEE_LIST}[ROW_ANY]  ==  ${Found}
  ${Delete_Selector}=  Format String  ${TO_EMPLOYEE_LIST}[BTN_DELETE_BY_ID]  id=${Employee_Id}
  Click  ${Delete_Selector}
  Wait For Screen  orangehrm.popup_confirmation  ${TO_DIALOG}[LBL_QUESTION]
  ${Deletion}=  Promise To  Wait For Response
  ...  matcher=**/api/v2/pim/employees
  ...  timeout=20s
  Click  ${TO_DIALOG}[BTN_CONFIRM_DELETE]
  Wait For  ${Deletion}
  Wait For Elements State  ${TO_DIALOG}[CTN_DIALOG]  detached  timeout=15s
  Employee Should Not Exist  ${Employee_Id}

Clean Up Created Employee
  [Documentation]  Teardown : ne supprime que ce que le test a créé, puis ferme le navigateur.
  ...  Sans matricule posé, le test n'a rien créé : il n'y a rien à nettoyer.
  [Arguments]  ${Employee_Id}
  TRY
    IF  '${Employee_Id}' != '${EMPTY}'  Delete Employee If Present  ${Employee_Id}
  FINALLY
    Close Browser
  END
