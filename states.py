from aiogram.fsm.state import StatesGroup, State

class MainMenuStates(StatesGroup):
    main = State()
    choose_language = State()
    choose_country = State()
    menu = State()
      
class CompareCarsStates(StatesGroup):
    selecting = State()

class AnalyzeAdStates(StatesGroup):
    waiting_for_ad = State()
    waiting_for_link = State()  # Додаємо цей стан
    waiting_for_pro_vin_input = State()

class CalcExpensesStates(StatesGroup):
    waiting_for_car = State()
    selecting = State()  # ← Додай цей стан!


class CarQuizStates(StatesGroup):
    answering = State()