"""
P1 Patch Unit Tests.

Проверяет:
1. month-only → dates_confirmed=False и следующий вопрос про числа
2. digits "5" при last_question_type=stars → stars=5
3. "на неделю" при last_question_type=nights → nights=7
4. hot_tours → вызывается hottours.php (мок _request)
5. запрет "проверил" если нет api_call_made
"""
import pytest
import asyncio
import sys
import os
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.nodes import extract_entities_regex, input_analyzer, generate_no_results_explanation
from app.agent.state import create_initial_state


# ==================== TEST 1: MONTH-ONLY DATES ====================

class TestMonthOnlyDates:
    """Тест: month-only даты НЕ подтверждаются."""
    
    def test_month_only_no_confirmation(self):
        """'в июле' → dates_confirmed=False, date_precision='month'"""
        entities = extract_entities_regex("Хочу в Турцию в июле")
        
        assert entities.get("date_from") is not None, "date_from должен быть установлен"
        assert entities.get("dates_confirmed") == False, "dates_confirmed должен быть False для month-only"
        assert entities.get("date_precision") == "month", "date_precision должен быть 'month'"
        assert entities.get("is_exact_date") == False, "is_exact_date должен быть False"
    
    def test_exact_date_confirmation(self):
        """'15 июля' → dates_confirmed=True, is_exact_date=True"""
        entities = extract_entities_regex("Хочу в Турцию 15 июля")
        
        assert entities.get("date_from") is not None, "date_from должен быть установлен"
        assert entities.get("dates_confirmed") == True, "dates_confirmed должен быть True для точной даты"
        assert entities.get("is_exact_date") == True, "is_exact_date должен быть True"
        assert entities.get("date_precision") == "exact", "date_precision должен быть 'exact'"
    
    def test_season_as_month_only(self):
        """'летом' → dates_confirmed=False (сезон = month-only)"""
        entities = extract_entities_regex("Хочу на море летом")
        
        assert entities.get("date_from") is not None, "date_from должен быть установлен"
        assert entities.get("dates_confirmed") == False, "dates_confirmed должен быть False для сезона"
        assert entities.get("date_precision") == "month", "date_precision должен быть 'month' для сезона"


# ==================== TEST 2: CONTEXT AWARENESS - STARS ====================

class TestContextAwarenessStars:
    """Тест: '5' при last_question_type=stars → stars=5"""
    
    @pytest.mark.asyncio
    async def test_digit_as_stars(self):
        """'5' в ответ на вопрос о звёздах → stars=5, stars_explicit=True"""
        state = create_initial_state()
        state["last_question_type"] = "stars"
        state["messages"] = [{"role": "user", "content": "5"}]
        state["search_params"] = {"destination_country": "Турция"}
        
        # Мокаем LLM чтобы не вызывать реальный API
        with patch('app.agent.nodes.extract_entities_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"intent": "search_tour", "entities": {}}
            
            result = await input_analyzer(state)
            
            assert result["search_params"].get("stars") == 5, "stars должен быть 5"
            assert result["search_params"].get("stars_explicit") == True, "stars_explicit должен быть True"
            assert result["last_question_type"] is None, "last_question_type должен быть сброшен"


# ==================== TEST 3: CONTEXT AWARENESS - NIGHTS ====================

class TestContextAwarenessNights:
    """Тест: 'на неделю' при last_question_type=nights → nights=7"""
    
    @pytest.mark.asyncio
    async def test_week_as_nights(self):
        """'на неделю' → nights=7"""
        state = create_initial_state()
        state["last_question_type"] = "nights"
        state["messages"] = [{"role": "user", "content": "на неделю"}]
        state["search_params"] = {"destination_country": "Турция"}
        
        with patch('app.agent.nodes.extract_entities_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"intent": "search_tour", "entities": {}}
            
            result = await input_analyzer(state)
            
            assert result["search_params"].get("nights") == 7, "nights должен быть 7"
            assert result["last_question_type"] is None, "last_question_type должен быть сброшен"
    
    @pytest.mark.asyncio
    async def test_two_weeks_as_nights(self):
        """'две недели' → nights=14"""
        state = create_initial_state()
        state["last_question_type"] = "nights"
        state["messages"] = [{"role": "user", "content": "две недели"}]
        state["search_params"] = {"destination_country": "Турция"}
        
        with patch('app.agent.nodes.extract_entities_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"intent": "search_tour", "entities": {}}
            
            result = await input_analyzer(state)
            
            assert result["search_params"].get("nights") == 14, "nights должен быть 14"
    
    @pytest.mark.asyncio
    async def test_digit_as_nights(self):
        """'7' в ответ на вопрос о ночах → nights=7"""
        state = create_initial_state()
        state["last_question_type"] = "nights"
        state["messages"] = [{"role": "user", "content": "7"}]
        state["search_params"] = {"destination_country": "Турция"}
        
        with patch('app.agent.nodes.extract_entities_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"intent": "search_tour", "entities": {}}
            
            result = await input_analyzer(state)
            
            assert result["search_params"].get("nights") == 7, "nights должен быть 7"


# ==================== TEST 4: HOT TOURS via HOTTOURS.PHP ====================

class TestHotToursEndpoint:
    """Тест: hot_tours → вызывается hottours.php"""
    
    @pytest.mark.asyncio
    async def test_hot_tours_uses_hottours_php(self):
        """Проверяем что горящие туры вызывают hottours.php"""
        from app.services.tourvisor import tourvisor_service
        
        # Мокаем _request чтобы проверить какой endpoint вызывается
        called_endpoints = []
        
        async def mock_request(endpoint, params):
            called_endpoints.append(endpoint)
            if endpoint == "hottours.php":
                return {
                    "data": {
                        "tour": [
                            {
                                "price": 50000,
                                "hotel": "Test Hotel",
                                "stars": 5,
                                "country": "Турция",
                                "countrycode": "TR",
                                "datebegin": "15.02.2026",
                                "nights": 7,
                                "meal": "AI",
                                "hotelid": 123
                            }
                        ]
                    }
                }
            return {"data": {}}
        
        with patch.object(tourvisor_service, '_request', side_effect=mock_request):
            with patch.object(tourvisor_service, 'mock_enabled', False):
                await tourvisor_service.load_countries()
                await tourvisor_service.load_departures()
                
                # Вызываем get_hot_tours
                tours = await tourvisor_service.get_hot_tours(
                    departure_id=1,
                    country_id=90,  # Турция
                    limit=5
                )
        
        assert "hottours.php" in called_endpoints, "hottours.php должен быть вызван"


# ==================== TEST 5: NO "ПРОВЕРИЛ" WITHOUT API CALL ====================

class TestNoProverilWithoutApi:
    """Тест: запрет 'проверил' если нет api_call_made"""
    
    def test_no_proveril_without_api(self):
        """Без api_call_made не говорим 'проверил'"""
        params = {
            "destination_country": "Турция",
            "departure_city": "Москва",
            "date_from": date(2026, 7, 15),
        }
        state = {
            "api_call_made": False,  # API не вызывался!
            "search_attempts": 1,
            "flex_days": 2,
            "flex_search": False,
        }
        
        response, await_agreement, action = generate_no_results_explanation(params, state)
        
        # Не должно быть слова "проверил"
        assert "проверил" not in response.lower(), "Не должно быть 'проверил' без API вызова"
        assert "уточните" in response.lower() or "параметры" in response.lower(), \
            "Должно быть сообщение об уточнении параметров"
    
    def test_proveril_with_api(self):
        """С api_call_made можно говорить 'проверил'"""
        params = {
            "destination_country": "Турция",
            "departure_city": "Москва",
            "date_from": date(2026, 7, 15),
        }
        state = {
            "api_call_made": True,  # API был вызван!
            "search_attempts": 2,
            "flex_days": 2,
            "flex_search": True,  # После расширения дат
            "offered_alt_departure": False,
        }
        
        response, await_agreement, action = generate_no_results_explanation(params, state)
        
        # Либо "проверил" в ответе, либо предложение альтернативы
        # (зависит от логики fallback)
        assert len(response) > 0, "Должен быть ответ"


# ==================== TEST 6: EXPLICIT FLAGS ====================

class TestExplicitFlags:
    """Тест: explicit флаги для фильтров"""
    
    def test_stars_explicit_flag(self):
        """'5 звёзд' → stars_explicit=True"""
        entities = extract_entities_regex("Хочу 5 звёзд всё включено")
        
        assert entities.get("stars") == 5, "stars должен быть 5"
        assert entities.get("stars_explicit") == True, "stars_explicit должен быть True"
    
    def test_food_explicit_flag(self):
        """'всё включено' → food_type_explicit=True"""
        entities = extract_entities_regex("Хочу 5 звёзд всё включено")
        
        assert entities.get("food_type") is not None, "food_type должен быть установлен"
        assert entities.get("food_type_explicit") == True, "food_type_explicit должен быть True"
    
    def test_no_implicit_stars(self):
        """Без явного указания stars_explicit=False"""
        entities = extract_entities_regex("Хочу в Турцию на неделю")
        
        assert entities.get("stars_explicit") != True, "stars_explicit не должен быть True без явного указания"


# ==================== MAIN ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
