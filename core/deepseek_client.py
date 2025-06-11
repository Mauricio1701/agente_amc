#deepseek_client.py
import os
import logging
import json
import re
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
from core.file_processor import process_file
from langchain_deepseek import ChatDeepSeek
from core.chat_history import ChatHistory
from datetime import datetime

logger = logging.getLogger(__name__)

class DeepSeekClient:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            logger.error("DEEPSEEK_API_KEY no encontrada en .env")
            raise ValueError("DEEPSEEK_API_KEY no configurada en las variables de entorno")

        # Inicializamos primero la base de datos
        from core.database import Database
        self.db = Database()

        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.7,
            max_tokens=2000,
            api_key=self.api_key
        )

        self.knowledge: List[Dict] = []
        self.amc_sql_guide: str = ""
        self.conversation_context: List[Dict] = []
        self.chat_history = ChatHistory()  # Añadir instancia de ChatHistory
        
        # Ahora sí cargamos el conocimiento
        self.load_knowledge()
        logger.info("DeepSeekClient inicializado correctamente")

    def load_knowledge(self):
        try:
            # Intentar cargar desde la base de datos primero
            db_knowledge = self.db.get_all_knowledge()
            if db_knowledge:
                # Asegurarnos de que last_accessed esté en formato string
                for item in db_knowledge:
                    if 'last_accessed' in item and isinstance(item['last_accessed'], datetime):
                        item['last_accessed'] = item['last_accessed'].isoformat()
                        
                self.knowledge = db_knowledge
                logger.info(f"Conocimiento cargado desde la base de datos: {len(self.knowledge)} temas")
                return
            
            # Si no hay datos en la base de datos, intentar cargar desde el archivo local
            if os.path.exists("knowledge.json"):
                with open("knowledge.json", "r", encoding="utf-8") as f:
                    self.knowledge = json.load(f)
                logger.info(f"Conocimiento cargado desde archivo local: {len(self.knowledge)} temas")
                
                # Asegurarnos de que last_accessed esté en formato string
                for item in self.knowledge:
                    if 'last_accessed' in item and isinstance(item['last_accessed'], datetime):
                        item['last_accessed'] = item['last_accessed'].isoformat()
                        
                # Guardar en la base de datos lo que se cargó del archivo local
                self.db.save_knowledge(self.knowledge)
            else:
                logger.info("No se encontraron datos de conocimiento, inicializando vacío")
                self.knowledge = []
        except Exception as e:
            logger.error(f"Error cargando conocimiento: {str(e)}")
            self.knowledge = []

    def save_knowledge(self) -> bool:
        """Guarda el conocimiento del cliente en archivo y base de datos."""
        try:
            # Guardar en el archivo local knowledge.json
            with open("knowledge.json", "w", encoding="utf-8") as f:
                json.dump(self.knowledge, f, indent=2, ensure_ascii=False)
            logger.info("Conocimiento guardado correctamente en archivo local")
            
            # Guardar en la base de datos
            if hasattr(self, 'db') and self.db:
                success = self.db.save_knowledge(self.knowledge)
                if success:
                    logger.info("Conocimiento guardado correctamente en la base de datos")
                else:
                    logger.error("Error al guardar conocimiento en la base de datos")
                    
            return True
        except Exception as e:
            logger.error(f"Error guardando conocimiento: {str(e)}")
            return False

    def clear_memory(self) -> str:
        self.knowledge = []
        self.conversation_context = []
        self.save_knowledge()
        logger.info("Memoria borrada exitosamente")
        return "Memoria borrada exitosamente"

    def _clean_response(self, text: str) -> str:
        text = re.sub(r'^\s*[\*\-]\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def improve_prompt(self, raw_prompt: str) -> str:
        corrections = {"campala": "campaña", "asin": "ASIN", "clientes": "nuevos clientes (new to brand)"}
        improved = raw_prompt.lower()
        for wrong, correct in corrections.items():
            improved = improved.replace(wrong, correct)
        term_map = {
            "ventas": "total_product_sales",
            "impresiones": "impressions",
            "clics": "clicks",
            "conversiones": "conversions",
            "campaña": "campaign",
            "región": "iso_state_province_code"
        }
        for term, mapped in term_map.items():
            improved = re.sub(r'\b' + term + r'\b', mapped, improved, flags=re.IGNORECASE)
        if "últimos" not in improved:
            improved += " en los últimos 30 días"
        improved = improved.capitalize().replace("_", " ")
        return f"Muestra las {improved}" if not improved.startswith("Muestra") else improved

    def chat(self, prompt: str, system: Optional[str] = None, use_file_context: bool = True, history: List[Dict] = None) -> str:
        prompt_lower = prompt.lower().strip()
        
        if prompt_lower in ["hola", "hola!", "hola.", "hola,"]:
            logger.info("Saludo detectado, respondiendo de forma profesional")
            self.conversation_context.append({"role": "user", "content": prompt})
            self.conversation_context.append({"role": "assistant", "content": "¡Hola! Soy tu asistente especializado en Amazon Marketing Cloud. ¿En qué puedo ayudarte hoy?"})
            return "¡Hola! Soy tu asistente especializado en Amazon Marketing Cloud. ¿En qué puedo ayudarte hoy?"

        if "mejorar el agente" in prompt_lower:
            logger.info("Consulta sobre mejorar el agente detectada")
            response = ("Para mejorar el asistente, he optimizado mi capacidad de análisis de datos de AMC. Puedo recordar nuestro historial de conversación para ofrecer respuestas más contextualizadas y proporcionar consultas SQL más precisas. ¿Te gustaría probar con un reporte específico de ventas o algún análisis en particular?")
            self.conversation_context.append({"role": "user", "content": prompt})
            self.conversation_context.append({"role": "assistant", "content": response})
            return response
        
        # Detectar si es una solicitud relacionada con consultas SQL de AMC
        is_amc_query = False
        amc_keywords = [
            'amc sql', 'consulta sql', 'query sql', 'reporte de', 'mostrar ventas', 'mostrar impresiones', 
            'mostrar clics', 'mostrar conversiones', 'dame un reporte', 'generar consulta', 'generar sql',
            'obtener datos de', 'métricas de', 'estadísticas de', 'conversion_event', 'traffic_event',
            'por campaña', 'por asin', 'por región', 'total_product_sales', 'impressions', 'genera una consulta',
            'quiero un reporte', 'necesito una consulta', 'crea un reporte', 'datos de ventas', 'datos de clics',
            'datos de impresiones', 'reporte sql', 'análisis de', 'analizar', 'muestrame', 'muéstrame',
            'consulta para ver', 'reporte para', 'ver datos de', 'compara', 'comparar'
        ]

        for keyword in amc_keywords:
            if keyword in prompt_lower:
                is_amc_query = True
                break

        if is_amc_query:
            logger.info("Detectada consulta relacionada con AMC SQL")
            try:
                # Generar la consulta SQL
                sql_query = self.generate_amc_sql(prompt)
                
                # Validar explícitamente que la consulta es válida para AMC
                if not self._is_valid_amc_sql(sql_query):
                    logger.warning(f"La consulta generada '{sql_query}' no cumple con las reglas de AMC, intentando regenerar")
                    # Intentar regenerar con instrucciones más específicas
                    clarified_prompt = (
                        f"Necesito una consulta AMC-SQL válida para: {prompt}\n\n"
                        f"IMPORTANTE: Recuerda que AMC-SQL tiene estas restricciones estrictas:\n"
                        f"1. No uses DATE_SUB, usa SECONDS_BETWEEN para filtros de tiempo (formato: SECONDS_BETWEEN(fecha1, CURRENT_DATE) <= 60*60*24*30)\n"
                        f"2. No uses INTERVAL ni funciones temporales no soportadas\n"
                        f"3. Siempre usa agregaciones (SUM, COUNT, AVG, etc.)\n"
                        f"4. Incluye GROUP BY para todas las columnas no agregadas\n"
                        f"5. No uses ORDER BY, SELECT * ni otras construcciones no soportadas\n"
                        f"6. Usa abreviaturas como alias de tablas (ej. 'c' para conversions)\n"
                        f"7. Elige la tabla correcta (dsp_clicks para clics, dsp_impressions para impresiones, etc.)"
                    )
                    sql_query = self.generate_amc_sql(clarified_prompt)
                    
                    # Verificar nuevamente
                    if not self._is_valid_amc_sql(sql_query):
                        logger.error("No se pudo generar una consulta SQL válida para AMC")
                        return "Lo siento, no pude generar una consulta SQL válida para Amazon Marketing Cloud con tu solicitud. Por favor, intenta reformular tu pregunta de manera más específica mencionando qué métricas (ventas, impresiones, clics) y dimensiones (ASIN, campaña, región) te interesan."
                
                # En la mayoría de los casos, queremos devolver solo la consulta SQL
                # Ampliar los casos donde se devuelve solo SQL sin explicación
                if not any(term in prompt_lower for term in ['explica', 'explícame', 'por qué', 'significado', 'enseñame', 'enseñar']):
                    # Devolver solo la consulta SQL formateada
                    answer = f"```sql\n{sql_query}\n```"
                    
                    # Guardar en historial
                    self.conversation_context.append({"role": "user", "content": prompt})
                    self.conversation_context.append({"role": "assistant", "content": answer})
                    self.chat_history.add_message(prompt, answer)
                    return answer
                
                # Caso contrario: crear una respuesta explicativa concisa
                system_context = (
                    "Eres un experto en Amazon Marketing Cloud. El usuario ha solicitado una consulta SQL. "
                    "Proporciona una respuesta breve y directa que:"
                    "1. Incluya la consulta SQL formateada en un bloque de código"
                    "2. Añada solo una explicación muy breve de lo que hace la consulta"
                    "No incluyas información adicional, pasos de implementación o notas extensas."
                )
                
                explanation_prompt = (
                    f"La consulta del usuario es: '{prompt}'\n\n"
                    f"He generado esta consulta SQL para AMC: {sql_query}\n\n"
                    "Proporciona la consulta SQL y una explicación breve de lo que hace (máximo 2 frases)."
                )
                
                messages = [
                    ("system", system_context),
                    ("human", explanation_prompt)
                ]
                
                # Obtener la explicación
                response = self.llm.invoke(messages)
                answer = response.content if hasattr(response, "content") else str(response)
                
                # Asegurarse de que la respuesta incluya la consulta SQL formateada
                if "```sql" not in answer:
                    # Si no hay bloque de código, poner la consulta SQL al principio
                    answer = f"```sql\n{sql_query}\n```\n\n{answer}"
                
                # Actualizar el contexto de la conversación
                self.conversation_context.append({"role": "user", "content": prompt})
                self.conversation_context.append({"role": "assistant", "content": answer})
                self._extract_knowledge(prompt, answer)
                self.chat_history.add_message(prompt, answer)
                return answer
            except Exception as e:
                logger.error(f"Error generando consulta AMC SQL: {str(e)}")
                # Continuar con el flujo normal en caso de error

        
        if system is None:
            system = (
                "Eres un asistente profesional especializado en Amazon Marketing Cloud (AMC). "
                "Usa un tono formal y experto, manteniendo un estilo claro y directo. "
                "Evita usar listas numeradas, asteriscos o guiones para estructurar tus respuestas; escribe en párrafos concisos. "
                "Si la consulta es simple, responde en no más de 100 palabras. "
                "Si es un análisis o consulta sobre AMC, proporciona información detallada y técnicamente precisa. "
                "Si el prompt es ambiguo, pide aclaraciones específicas para ofrecer la mejor respuesta posible."
            )

        messages = [("system", system)]

        if use_file_context and self.knowledge:
            context = "\n".join(
                f"Conocimiento sobre {item['topic']}: {', '.join(item['facts'])}"
                for item in sorted(self.knowledge, key=lambda x: x.get('last_accessed', ''), reverse=True)[:5]
            )
            messages.append(("system", f"Conocimiento previo relevante:\n{context[:2000]}"))

        if history:
            for message in history[-5:]:
                messages.append(("user" if message["role"] == "user" else "assistant", message["content"]))

        messages.append(("human", prompt))

        try:
            response = self.llm.invoke(messages)
            answer = response.content if hasattr(response, "content") else str(response)
            answer = self._clean_response(answer)

            if "reporte" in prompt_lower or "ventas" in prompt_lower or "impresiones" in prompt_lower or "clics" in prompt_lower:
                if not re.search(r"\b(por|en)\b", prompt_lower):
                    answer = "Su consulta parece relacionarse con reportes de AMC, pero no detecto una dimensión clara para agrupar los datos. ¿Le gustaría un reporte por campaña, por ASIN, por región o alguna otra dimensión específica? Con esa información podré proporcionarle un análisis más preciso."

            self.conversation_context.append({"role": "user", "content": prompt})
            self.conversation_context.append({"role": "assistant", "content": answer})
            self._extract_knowledge(prompt, answer)
            self.chat_history.add_message(prompt, answer)
            return answer
        except Exception as e:
            logger.error(f"Error en chat: {str(e)}")
            return f"Se ha producido un error al procesar su solicitud. Por favor, inténtelo de nuevo o reformule su consulta."
        
    def generate_amc_sql(self, natural_query: str, max_retries: int = 3) -> str:
        system_prompt = (
            "Eres un experto en AMC-SQL (Amazon Marketing Cloud SQL). Convierte solicitudes en lenguaje natural sobre reportes de Amazon AMC "
            "(como ventas, conversiones, impresiones, clics, vistas de video, etc.) en consultas AMC-SQL válidas. Usa las siguientes tablas y campos:\n"
            "- **conversions**: combined_sales, conversion_event_name, conversion_event_source_name, conversion_id, conversions, event_category, "
            "event_date_utc, event_day_utc, event_dt_hour_utc, event_dt_utc, event_hour_utc, event_subtype, event_type, event_type_class, "
            "event_type_description, marketplace_id, marketplace_name, new_to_brand, no_3p_trackers, off_amazon_conversion_value, "
            "off_amazon_product_sales, purchase_currency, purchase_unit_price, total_product_sales, total_units_sold, tracked_asin, "
            "tracked_item, user_id, user_id_type.\n"
            "- **conversions_with_relevance**: advertiser, advertiser_id, advertiser_timezone, campaign, campaign_budget_amount, "
            "campaign_end_date, campaign_end_date_utc, campaign_end_dt, campaign_end_dt_utc, campaign_id, campaign_id_string, "
            "campaign_sales_type, campaign_source, campaign_start_date, campaign_start_date_utc, campaign_start_dt, campaign_start_dt_utc, "
            "combined_sales, conversion_event_name, conversion_event_source_name, conversion_id, conversions, engagement_scope, "
            "event_category, event_date, event_date_utc, event_day, event_day_utc, event_dt, event_dt_hour, event_dt_hour_utc, event_dt_utc, "
            "event_hour, event_hour_utc, event_subtype, event_type, event_type_class, event_type_description, halo_code, marketplace_id, "
            "marketplace_name, new_to_brand, no_3p_trackers, off_amazon_conversion_value, off_amazon_product_sales, purchase_currency, "
            "purchase_unit_price, total_product_sales, total_units_sold, tracked_asin, tracked_item, user_id, user_id_type.\n"
            "- **amazon_attributed_events_by_conversion_time** y **amazon_attributed_events_by_traffic_time**: ad_product_type, ad_slot_size, "
            "add_to_cart, add_to_cart_clicks, add_to_cart_views, advertiser, advertiser_conversion_definition_dim_id, advertiser_id, "
            "advertiser_id_internal, advertiser_timezone, audience_fee, bid_price, brand_halo_add_to_cart, brand_halo_add_to_cart_views, "
            "brand_halo_detail_page_view, brand_halo_detail_page_view_clicks, brand_halo_detail_page_view_views, brand_halo_product_sales, "
            "brand_halo_product_sales_clicks, brand_halo_product_sales_views, brand_halo_purchases, brand_halo_purchases_clicks, "
            "brand_halo_purchases_views, brand_halo_units_sold, brand_halo_units_sold_clicks, brand_halo_units_sold_views, browser_family, "
            "campaign, campaign_budget_amount, campaign_end_date, campaign_end_date_utc, campaign_end_dt, campaign_end_dt_utc, "
            "campaign_flight_id, campaign_id, campaign_id_string, campaign_insertion_order_id, campaign_primary_goal, campaign_start_date, "
            "campaign_start_date_utc, campaign_status, city_name, click_cost, click_date, click_date_utc, click_day, click_day_utc, click_dt, "
            "click_dt_hour, click_dt_hour_utc, click_dt_utc, click_hour, click_hour_utc, clicks, combined_sales, conversion_event_category, "
            "conversion_event_date, conversion_event_date_utc, conversion_event_dt, conversion_event_dt_hour, conversion_event_dt_hour_utc, "
            "conversion_event_dt_utc, conversion_event_hour, conversion_event_hour_utc, conversion_event_marketplace_id, "
            "conversion_event_marketplace_name, conversion_event_name, conversion_event_source_name, conversion_event_subtype, "
            "conversion_event_type, conversion_event_type_class, conversion_event_type_description, conversions, creative, creative_category, "
            "creative_duration, creative_id, creative_is_link_in, creative_size, creative_type, customer_search_term, deal_id, deal_name, "
            "detail_page_view_clicks, detail_page_view_views, device_make, device_model, device_type, digital_app_subscription_signup_purchases, "
            "digital_free_trial_app_subscription_signup_purchases, digital_free_trial_subscription_signup_purchases, "
            "digital_paid_app_subscription_signup_purchases, digital_paid_subscription_signup_purchases, digital_subscription_signup_purchases, "
            "dma_code, entity_id, environment_type, impression_date, impression_date_utc, impression_day, impression_day_utc, impression_dt, "
            "impression_dt_hour, impression_dt_hour_utc, impression_dt_utc, impression_hour, impression_hour_utc, impressions, "
            "is_event_type_modeled_view, iso_country_code, iso_state_province_code, line_item, line_item_budget_amount, line_item_end_date, "
            "line_item_end_date_utc, line_item_id, line_item_start_date, line_item_start_date_utc, line_item_status, line_item_type, "
            "match_type, new_to_brand, new_to_brand_brand_halo_product_sales, new_to_brand_brand_halo_purchases, "
            "new_to_brand_brand_halo_units_sold, new_to_brand_product_sales, new_to_brand_purchases, new_to_brand_total_product_sales, "
            "new_to_brand_total_purchases, new_to_brand_total_units_sold, new_to_brand_units_sold, no_3p_trackers, off_amazon_conversion_value, "
            "off_amazon_product_sales, operating_system, os_version, page_type, pixel_accept, pixel_accept_clicks, pixel_accept_views, "
            "pixel_add_to_shopping_cart, pixel_add_to_shopping_cart_clicks, pixel_add_to_shopping_cart_views, pixel_application, "
            "pixel_application_clicks, pixel_application_views, pixel_banner_interaction, pixel_banner_interaction_clicks, "
            "pixel_banner_interaction_views, pixel_brand_store_engagement_1, pixel_brand_store_engagement_1_clicks, "
            "pixel_brand_store_engagement_1_views, pixel_brand_store_engagement_2, pixel_brand_store_engagement_2_clicks, "
            "pixel_brand_store_engagement_2_views, pixel_brand_store_engagement_3, pixel_brand_store_engagement_3_clicks, "
            "pixel_brand_store_engagement_3_views, pixel_brand_store_engagement_4, pixel_brand_store_engagement_4_clicks, "
            "pixel_brand_store_engagement_4_views, pixel_brand_store_engagement_5, pixel_brand_store_engagement_5_clicks, "
            "pixel_brand_store_engagement_5_views, pixel_brand_store_engagement_6, pixel_brand_store_engagement_6_clicks, "
            "pixel_brand_store_engagement_6_views, pixel_brand_store_engagement_7, pixel_brand_store_engagement_7_clicks, "
            "pixel_brand_store_engagement_7_views, pixel_click_on_redirect, pixel_click_on_redirect_clicks, pixel_click_on_redirect_views, "
            "pixel_decline, pixel_decline_clicks, pixel_decline_views, pixel_drop_down_selection, pixel_drop_down_selection_clicks, "
            "pixel_drop_down_selection_views, pixel_email_interaction, pixel_email_interaction_clicks, pixel_email_interaction_views, "
            "pixel_email_load, pixel_email_load_clicks, pixel_email_load_views, pixel_game_interaction, pixel_game_interaction_clicks, "
            "pixel_game_interaction_views, pixel_game_load, pixel_game_load_clicks, pixel_game_load_views, pixel_homepage_visit, "
            "pixel_homepage_visit_clicks, pixel_homepage_visit_views, pixel_marketing_landing_page, pixel_marketing_landing_page_clicks, "
            "pixel_marketing_landing_page_views, pixel_mashup_add_to_cart, pixel_mashup_add_to_cart_clicks, pixel_mashup_add_to_cart_views, "
            "pixel_mashup_add_to_wishlist, pixel_mashup_add_to_wishlist_clicks, pixel_mashup_add_to_wishlist_views, "
            "pixel_mashup_backup_image, pixel_mashup_backup_image_clicks, pixel_mashup_backup_image_views, pixel_mashup_click_to_page, "
            "pixel_mashup_click_to_page_clicks, pixel_mashup_click_to_page_views, pixel_mashup_clip_coupon, pixel_mashup_clip_coupon_clicks, "
            "pixel_mashup_clip_coupon_views, pixel_mashup_shop_now, pixel_mashup_shop_now_clicks, pixel_mashup_shop_now_views, "
            "pixel_mashup_subscribe_and_save, pixel_mashup_subscribe_and_save_clicks, pixel_mashup_subscribe_and_save_views, "
            "pixel_message_sent, pixel_message_sent_clicks, pixel_message_sent_views, pixel_mobile_app_first_start, "
            "pixel_mobile_app_first_start_clicks, pixel_mobile_app_first_start_views, pixel_product_purchased, "
            "pixel_product_purchased_clicks, pixel_product_purchased_views, pixel_purchase_button, pixel_purchase_button_clicks, "
            "pixel_purchase_button_views, pixel_referral, pixel_referral_clicks, pixel_referral_views, pixel_registration_confirm_page, "
            "pixel_registration_confirm_page_clicks, pixel_registration_confirm_page_views, pixel_registration_form, "
            "pixel_registration_form_clicks, pixel_registration_form_views, pixel_sign_up_button, pixel_sign_up_button_clicks, "
            "pixel_sign_up_button_views, pixel_sign_up_page, pixel_sign_up_page_clicks, pixel_sign_up_page_views, "
            "pixel_store_locator_page, pixel_store_locator_page_clicks, pixel_store_locator_page_views, pixel_submit_button, "
            "pixel_submit_button_clicks, pixel_submit_button_views, pixel_subscription_button, pixel_subscription_button_clicks, "
            "pixel_subscription_button_views, pixel_subscription_page, pixel_subscription_page_clicks, pixel_subscription_page_views, "
            "pixel_success_page, pixel_success_page_clicks, pixel_success_page_views, pixel_survey_finish, pixel_survey_finish_clicks, "
            "pixel_survey_finish_views, pixel_survey_start, pixel_survey_start_clicks, pixel_survey_start_views, pixel_thank_you_page, "
            "pixel_thank_you_page_clicks, pixel_thank_you_page_views, pixel_video_end, pixel_video_end_clicks, pixel_video_end_views, "
            "pixel_video_started, pixel_video_started_clicks, pixel_video_started_views, pixel_widget_interaction, "
            "pixel_widget_interaction_clicks, pixel_widget_interaction_views, pixel_widget_load, pixel_widget_load_clicks, "
            "pixel_widget_load_views, placement_type, platform_fee, postal_code, product_line, product_sales, product_sales_clicks, "
            "product_sales_views, purchase_currency, purchase_price, purchase_quantity, purchase_retail_program, purchase_unit_price, "
            "purchases, purchases_clicks, purchases_views, request_tag, site, supply_cost, supply_source, targeting, total_add_to_cart, "
            "total_add_to_cart_clicks, total_add_to_cart_views, total_detail_page_view, total_detail_page_view_clicks, "
            "total_detail_page_view_views, total_product_sales, total_product_sales_clicks, total_product_sales_views, total_purchases, "
            "total_purchases_clicks, total_purchases_views, total_units_sold, total_units_sold_clicks, total_units_sold_views, tracked_asin, "
            "tracked_item, traffic_event_date, traffic_event_date_utc, traffic_event_dt, traffic_event_dt_hour, traffic_event_dt_hour_utc, "
            "traffic_event_dt_utc, traffic_event_hour, traffic_event_hour_utc, traffic_event_id, traffic_event_marketplace_id, "
            "traffic_event_marketplace_name, traffic_event_subtype, traffic_event_type, units_sold, units_sold_clicks, units_sold_views, "
            "user_id, user_id_type, winning_bid_cost.\n"
            "- **dsp_impressions**, **dsp_impressions_by_matched_segments**, **dsp_impressions_by_user_segments**: ad_slot_size, advertiser, "
            "advertiser_country, advertiser_id, advertiser_timezone, app_bundle, audience_fee, behavior_segment_description, "
            "behavior_segment_id, behavior_segment_matched, behavior_segment_name, bid_price, browser_family, campaign, "
            "campaign_budget_amount, campaign_end_date, campaign_end_date_utc, campaign_flight_id, campaign_id, campaign_id_string, "
            "campaign_insertion_order_id, campaign_primary_goal, campaign_sales_type, campaign_source, campaign_start_date, "
            "campaign_start_date_utc, campaign_status, city_name, creative, creative_category, creative_duration, creative_id, "
            "creative_is_link_in, creative_size, creative_type, currency_iso_code, currency_name, deal_id, deal_name, demand_channel, "
            "demand_channel_owner, device_id, device_make, device_model, device_type, dma_code, entity_id, environment_type, "
            "impression_cost, impression_date, impression_date_utc, impression_day, impression_day_utc, impression_dt, "
            "impression_dt_hour, impression_dt_hour_utc, impression_dt_utc, impression_hour, impression_hour_utc, impressions, "
            "is_amazon_owned, iso_country_code, iso_state_province_code, line_item, line_item_budget_amount, line_item_end_date, "
            "line_item_end_date_utc, line_item_id, line_item_price_type, line_item_start_date, line_item_start_date_utc, "
            "line_item_status, line_item_type, managed_service_fee, matched_behavior_segment_ids, merchant_id, no_3p_trackers, "
            "ocm_fee, operating_system, os_version, page_type, placement_is_view_aware, placement_view_rate, platform_fee, "
            "postal_code, product_line, publisher_id, request_tag, segment_marketplace_id, site, slot_position, supply_cost, "
            "supply_source, supply_source_id, supply_source_is_view_aware, supply_source_view_rate, third_party_fees, total_cost, "
            "user_behavior_segment_ids, user_id, user_id_type, winning_bid_cost.\n"
            "- **dsp_clicks**: ad_slot_size, advertiser, advertiser_country, advertiser_id, advertiser_timezone, app_bundle, audience_fee, "
            "bid_price, browser_family, campaign, campaign_budget_amount, campaign_end_date, campaign_end_date_utc, campaign_flight_id, "
            "campaign_id, campaign_id_string, campaign_insertion_order_id, campaign_primary_goal, campaign_sales_type, campaign_source, "
            "campaign_start_date, campaign_start_date_utc, campaign_status, city_name, click_cost, click_date, click_date_utc, click_day, "
            "click_day_utc, click_dt, click_dt_hour, click_dt_hour_utc, click_dt_utc, click_hour, click_hour_utc, clicks, creative, "
            "creative_category, creative_duration, creative_id, creative_is_link_in, creative_size, creative_type, currency_iso_code, "
            "currency_name, deal_id, deal_name, demand_channel, demand_channel_owner, device_id, device_make, device_model, device_type, "
            "dma_code, entity_id, environment_type, impression_date, impression_date_utc, impression_day, impression_day_utc, impression_dt, "
            "impression_dt_hour, impression_dt_hour_utc, impression_dt_utc, impression_hour, impression_hour_utc, is_amazon_owned, "
            "iso_country_code, iso_state_province_code, line_item, line_item_budget_amount, line_item_end_date, line_item_end_date_utc, "
            "line_item_id, line_item_price_type, line_item_start_date, line_item_start_date_utc, line_item_status, line_item_type, "
            "merchant_id, no_3p_trackers, operating_system, os_version, page_type, platform_fee, postal_code, product_line, publisher_id, "
            "request_tag, site, slot_position, supply_cost, supply_source, supply_source_id, user_id, user_id_type, winning_bid_cost.\n"
            "- **dsp_video_events_feed**: ad_slot_size, advertiser, advertiser_country, advertiser_id, advertiser_timezone, app_bundle, "
            "audience_fee, bid_price, browser_family, campaign, campaign_budget_amount, campaign_end_date, campaign_end_date_utc, "
            "campaign_flight_id, campaign_id, campaign_id_string, campaign_insertion_order_id, campaign_primary_goal, campaign_sales_type, "
            "campaign_source, campaign_start_date, campaign_start_date_utc, campaign_status, city_name, video_click, video_complete, "
            "video_creative_view, video_first_quartile, video_impression, video_midpoint, video_mute, video_pause, video_replay, "
            "video_resume, video_skip_backward, video_skip_forward, video_start, video_third_quartile, video_unmute.\n"
            "- **dsp_views**: campaign_end_dt, campaign_end_dt_utc, campaign_start_dt, campaign_start_dt_utc, event_date, event_date_utc, "
            "event_dt, event_dt_hour, event_dt_hour_utc, event_dt_utc, event_type, events, impression_id, line_item, line_item_end_dt, "
            "line_item_end_dt_utc, line_item_id, line_item_price_type, line_item_start_dt, line_item_start_dt_utc, line_item_status, "
            "line_item_type, measurable_impressions, merchant_id, no_3p_trackers, operating_system, os_version, page_type, publisher_id, "
            "site, slot_position, supply_source_id, unmeasurable_viewable_impressions, user_id, user_id_type, view_definition, "
            "viewable_impressions, winning_bid_amount.\n"
            "- **sponsored_ads_traffic**: ad_group, ad_group_end_dt, ad_group_end_dt_utc, ad_group_start_dt, ad_group_start_dt_utc, "
            "ad_group_status, ad_group_type, ad_product_type, ad_product_type_code, ad_product_type_id, advertiser, advertiser_id_internal, "
            "advertiser_timezone, campaign, campaign_budget_type, campaign_end_date, campaign_end_date_utc, campaign_end_dt, "
            "campaign_end_dt_utc, campaign_id, campaign_id_string, campaign_start_date, campaign_start_date_utc, campaign_start_dt, "
            "campaign_start_dt_utc, clicks, creative, creative_type, currency_iso_code, currency_name, customer_search_term, entity_id, "
            "event_date, event_date_utc, event_day, event_day_utc, event_dt, event_dt_hour, event_dt_hour_utc, event_dt_utc, event_hour, "
            "event_hour_utc, event_id, five_sec_views, impressions, line_item, line_item_end_date, line_item_end_date_utc, line_item_id, "
            "line_item_price_type, line_item_start_date, line_item_start_date_utc, line_item_status, line_item_type, marketplace_id, "
            "marketplace_name, match_type, matched_behavior_segment_ids, no_3p_trackers, operating_system, os_version, placement_type, "
            "spend, targeting, unmeasurable_viewable_impressions, user_id, user_id_type, video_complete_views, video_first_quartile_views, "
            "video_midpoint_views, video_third_quartile_views, video_unmutes, view_definition, viewable_impressions.\n"
            "- **Tablas de suscripción (subscription tables)**:\n"
            "  Estas tablas contienen información detallada sobre compras minoristas y segmentaciones de audiencia para análisis de suscripción.\n"
            "  - **amazon_retail_purchases**: asin, asin_brand, asin_name, asin_parent, currency_code, event_id, is_business_flag, is_gift_flag, marketplace_id, marketplace_name, no_3p_trackers, origin_session_id, purchase_date_utc, purchase_day_utc, purchase_dt_hour_utc, purchase_dt_utc, purchase_hour_utc, purchase_id, purchase_month_utc, purchase_order_method, purchase_order_type, purchase_program_name, purchase_session_id, purchase_units_sold, unit_price, user_id, user_id_type.\n"
            "  - **audience_segments_amer_inmarket**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, user_id, user_id_type.\n"
            "  - **audience_segments_amer_inmarket_snapshot**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, snapshot_datetime, user_id, user_id_type.\n"
            "  - **audience_segments_amer_lifestyle**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, user_id, user_id_type.\n"
            "  - **audience_segments_amer_lifestyle_snapshot**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, snapshot_datetime, user_id, user_id_type.\n"
            "  - **audience_segments_apac_inmarket**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, user_id, user_id_type.\n"
            "  - **audience_segments_apac_inmarket_snapshot**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, snapshot_datetime, user_id, user_id_type.\n"
            "  - **audience_segments_apac_lifestyle**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, user_id, user_id_type.\n"
            "  - **audience_segments_apac_lifestyle_snapshot**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, snapshot_datetime, user_id, user_id_type.\n"
            "  - **audience_segments_eu_inmarket**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, user_id, user_id_type.\n"
            "  - **audience_segments_eu_inmarket_snapshot**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, snapshot_datetime, user_id, user_id_type.\n"
            "  - **audience_segments_eu_lifestyle**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, user_id, user_id_type.\n"
            "  - **audience_segments_eu_lifestyle_snapshot**: no_3p_trackers, segment_id, segment_marketplace_id, segment_name, snapshot_datetime, user_id, user_id_type.\n"
            "  - **conversions_all**: combined_sales, conversion_event_name, conversion_event_source_name, conversion_id, conversions, event_category, event_date_utc, event_day_utc, event_dt_hour_utc, event_dt_utc, event_hour_utc, event_subtype, event_type, event_type_class, event_type_description, exposure_type, marketplace_id, marketplace_name, new_to_brand, no_3p_trackers, off_amazon_conversion_value, off_amazon_product_sales, purchase_currency, purchase_unit_price, sns_subscription_id, total_product_sales, total_units_sold, tracked_asin, tracked_item, user_id, user_id_type.\n"
            "  - **segment_metadata**: category_level_1, category_level_2, category_path, no_3p_trackers, segment_description, segment_id, segment_marketplace_id, segment_name.\n"
            "**Reglas de AMC-SQL**:\n"
            "- Siempre incluye una función de agregación (SUM, COUNT, AVG, MIN, MAX) para métricas como total_product_sales, impressions, clicks, conversions.\n"
            "- Todas las dimensiones en SELECT (ej. tracked_asin, campaign, iso_state_province_code) deben estar en GROUP BY.\n"
            "- No uses SELECT *, ORDER BY, DATE_DIFF, FLOOR ni funciones no admitidas.\n"
            "- Para filtros de tiempo (ej. 'los últimos 7 días'), usa SECONDS_BETWEEN(fecha_1, fecha_2) <= 60 * 60 * 24 * X. Por ejemplo, para eventos con diferencia máxima de 9 días: SECONDS_BETWEEN(traffic_event_dt_utc, conversion_event_dt_utc) <= 60 * 60 * 24 * 9. Evita usar DATE_SUB, ya que no está soportado por AMC.\n"
            "- Usa CASE WHEN para segmentaciones (ej. exposure_type: CASE WHEN exposure_type = 'ad-exposed' THEN total_product_sales ELSE 0 END).\n"
            "- Para diferencias temporales entre eventos, usa SECONDS_BETWEEN (ej. SECONDS_BETWEEN(traffic_event_dt_utc, conversion_event_dt_utc)).\n"
            "- Siempre asigna un alias corto a cada tabla (ej. 'c' para conversions, 'aet' para amazon_attributed_events_by_traffic_time) y usa ese alias en todas las columnas del SELECT, WHERE y GROUP BY.\n"
            "**Instrucciones**:\n"
            "1. Identifica las dimensiones (ej. campaign, tracked_asin, iso_state_province_code), métricas (ej. total_product_sales, impressions, clicks) y filtros (ej. fechas, condiciones) en la solicitud.\n"
            "2. Selecciona la tabla adecuada según la solicitud:\n"
            "   - Usa conversions o conversions_with_relevance para conversiones y ventas.\n"
            "   - Usa amazon_attributed_events_by_conversion_time o amazon_attributed_events_by_traffic_time para eventos atribuidos (ventas, conversiones, clics).\n"
            "   - Usa dsp_impressions, dsp_impressions_by_matched_segments, o dsp_impressions_by_user_segments para impresiones y segmentos.\n"
            "   - Usa dsp_clicks para clics.\n"
            "   - Usa dsp_video_events_feed para métricas de video (video_start, video_complete).\n"
            "   - Usa dsp_views para vistas.\n"
            "   - Usa sponsored_ads_traffic para tráfico de anuncios patrocinados.\n"
            "3. Si el usuario especifica valores concretos (como nombres de campañas, ASIN, regiones, tipos de dispositivos, etc.), inclúyelos como filtros en la consulta usando WHERE (ej. WHERE campaign = 'SummerPromo2025' o WHERE tracked_asin IN ('ASIN12345', 'ASIN67890')).\n"
            "4. Genera una consulta AMC-SQL válida con SELECT, FROM, WHERE (si aplica), y GROUP BY. Devuelve solo la consulta SQL limpia, sin explicaciones ni bloques de código.\n"
            "**Ejemplos**:\n"
            "- 'Ventas por ASIN para clientes expuestos y no expuestos': SELECT c.tracked_asin, SUM(c.total_product_sales) AS total_sales, "
            "SUM(CASE WHEN c.exposure_type = 'ad-exposed' THEN c.total_product_sales ELSE 0 END) AS exposed_sales, "
            "SUM(CASE WHEN c.exposure_type = 'non-ad-exposed' THEN c.total_product_sales ELSE 0 END) AS non_exposed_sales FROM conversions c GROUP BY c.tracked_asin;\n"
            "- 'Impresiones por campaña en los últimos 7 días': SELECT di.campaign, SUM(di.impressions) AS total_impressions FROM dsp_impressions di "
            "WHERE SECONDS_BETWEEN(di.impression_date_utc, CURRENT_DATE) <= 60 * 60 * 24 * 7 GROUP BY di.campaign;\n"
            "- 'Conversiones por campaña SummerPromo2025': SELECT cwr.campaign, SUM(cwr.conversions) AS total_conversions FROM conversions_with_relevance cwr "
            "WHERE cwr.campaign = 'SummerPromo2025' GROUP BY cwr.campaign;\n"
            "- 'Número de clics por región CA': SELECT dc.iso_state_province_code, SUM(dc.clicks) AS total_clicks FROM dsp_clicks dc "
            "WHERE dc.iso_state_province_code = 'CA' GROUP BY dc.iso_state_province_code;\n"
            "- 'Vistas de video completadas por campaña': SELECT dv.campaign, SUM(dv.video_complete) AS total_video_completes FROM dsp_video_events_feed dv "
            "GROUP BY dv.campaign;\n"
            "- 'Ventas por ASIN con diferencia máxima de 24 horas entre impresión y conversión': SELECT aet.tracked_asin, SUM(aet.total_product_sales) AS total_sales "
            "FROM amazon_attributed_events_by_traffic_time aet WHERE SECONDS_BETWEEN(aet.traffic_event_dt_utc, aet.conversion_event_dt_utc) <= 60 * 60 * 24 "
            "GROUP BY aet.tracked_asin;"
            "**IMPORTANTE: Restricciones estrictas de tablas y columnas en AMC:**\n"
            "1. Para consultas sobre impresiones, usa SOLO la tabla dsp_impressions y su columna impressions\n"
            "2. Para consultas sobre clics, usa SOLO la tabla dsp_clicks y su columna clicks\n" 
            "3. Para consultas sobre conversiones o ventas, usa SOLO las tablas conversions o conversions_with_relevance con sus columnas conversions y total_product_sales\n"
            "4. Para eventos de video, usa SOLO la tabla dsp_video_events_feed con sus columnas específicas de video\n"
            "5. NUNCA mezcles columnas de una tabla en otra tabla (ej: NO consultes impressions en conversions_with_relevance)\n"
            "6. Si necesitas datos de múltiples tipos de eventos (impresiones, clics y conversiones), crea consultas separadas\n"
            "7. Para cada métrica, escoge la tabla correcta: dsp_impressions para impresiones, dsp_clicks para clics, conversions_with_relevance para conversiones\n"
            "8. RECUERDA: 'impressions' SOLO existe en dsp_impressions, 'clicks' SOLO existe en dsp_clicks, 'conversions' y 'total_product_sales' SOLO existen en conversions y conversions_with_relevance\n"
            
            "**Ejemplos CORRECTOS (cada métrica en su tabla correspondiente):**\n"
            "- Impresiones por campaña: SELECT di.campaign, SUM(di.impressions) AS total_impressions FROM dsp_impressions di GROUP BY di.campaign;\n"
            "- Clics por campaña: SELECT dc.campaign, SUM(dc.clicks) AS total_clicks FROM dsp_clicks dc GROUP BY dc.campaign;\n"
            "- Conversiones por campaña: SELECT cwr.campaign, SUM(cwr.conversions) AS total_conversions, SUM(cwr.total_product_sales) AS total_sales FROM conversions_with_relevance cwr GROUP BY cwr.campaign;\n"
            
            "**Ejemplos INCORRECTOS (causan error):**\n"
            "- ERROR: SELECT cwr.campaign, SUM(cwr.impressions) AS total_impressions FROM conversions_with_relevance cwr GROUP BY cwr.campaign; -- impressions NO existe en conversions_with_relevance\n"
            "- ERROR: SELECT di.campaign, SUM(di.clicks) AS total_clicks FROM dsp_impressions di GROUP BY di.campaign; -- clicks NO existe en dsp_impressions\n"
            
            "Si la consulta pide múltiples métricas (impresiones, clics y conversiones) para una misma dimensión (ej. campaña), genera SOLO UNA consulta para la métrica principal solicitada. Explica en tu respuesta que cada métrica debe consultarse por separado.\n"
        )
        

        messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Guía de AMC-SQL:\n{self.amc_sql_guide[:5000]}..."},
        {"role": "user", "content": f"Genera una consulta AMC-SQL para: {natural_query}. Asegúrate de que cada columna exista en la tabla que estás utilizando. Si necesito impresiones, usa dsp_impressions. Si necesito clics, usa dsp_clicks. Si necesito conversiones o ventas, usa conversions o conversions_with_relevance."}
    ]

        for attempt in range(max_retries):
            try:
                response = self.llm.invoke(messages)
                sql_query = response.content if hasattr(response, "content") else str(response)
                sql_query = re.sub(r'```sql\s*|\s*```|\n\s*\n', '', sql_query).strip()
                
                # Verificar si la consulta mezcla columnas de diferentes tablas incorrectamente
                if self._has_invalid_column_usage(sql_query):
                    logger.warning(f"Intento {attempt+1}: Consulta usa columnas incorrectas para la tabla seleccionada, regenerando...")
                    
                    # Añadir instrucción más específica para el próximo intento
                    correction_prompt = (
                        f"La consulta generada contiene un error: estás usando columnas que no existen en la tabla seleccionada.\n\n"
                        f"Consulta errónea: {sql_query}\n\n"
                        f"RECUERDA:\n"
                        f"- La columna 'impressions' SOLO existe en la tabla dsp_impressions\n"
                        f"- La columna 'clicks' SOLO existe en la tabla dsp_clicks\n"
                        f"- Las columnas 'conversions' y 'total_product_sales' SOLO existen en conversions y conversions_with_relevance\n\n"
                        f"Genera una nueva consulta AMC-SQL para: {natural_query}\n"
                        f"Asegúrate de usar la tabla correcta para cada métrica."
                    )
                    messages.append({"role": "user", "content": correction_prompt})
                    continue
                    
                if not self._is_valid_amc_sql(sql_query):
                    logger.warning(f"Intento {attempt+1}: Consulta generada no válida, regenerando...")
                    continue
                    
                return sql_query
            except Exception as e:
                logger.error(f"Error generando AMC-SQL: {str(e)}")
                if attempt == max_retries - 1:
                    return f"Error al generar la consulta SQL: {str(e)}"
                continue
        
        # Si llegamos aquí, todos los intentos fallaron
        return "No pude generar una consulta SQL válida después de varios intentos. Por favor, reformula tu solicitud especificando claramente qué métricas necesitas (impresiones, clics o conversiones)."


    def _is_valid_amc_sql(self, sql_query: str) -> bool:
        """Verifica que la consulta SQL cumple con las restricciones de AMC."""
        sql_upper = sql_query.upper()
        
        # Verificaciones básicas de estructura
        if "SELECT" not in sql_upper or "FROM" not in sql_upper:
            logger.warning("Consulta SQL sin SELECT o FROM")
            return False
            
        # Verificar que tiene GROUP BY si hay columnas no agregadas
        if "GROUP BY" not in sql_upper:
            logger.warning("Consulta SQL sin GROUP BY")
            return False
            
        # Verificar que no usa construcciones prohibidas
        prohibited = ["SELECT *", "ORDER BY", "DATE_SUB", "DATE_DIFF", "FLOOR", "INTERVAL"]
        for term in prohibited:
            if term in sql_upper:
                logger.warning(f"Consulta SQL usa término prohibido: {term}")
                return False
        
        # Verificar que usa funciones de agregación
        if not any(agg in sql_upper for agg in ["SUM(", "COUNT(", "AVG(", "MIN(", "MAX("]):
            logger.warning("Consulta SQL sin funciones de agregación")
            return False
            
        # Verificar que los filtros de tiempo usan SECONDS_BETWEEN correctamente
        if "ÚLTIMOS" in sql_upper or "ULTIMOS" in sql_upper or "RECIENTES" in sql_upper:
            if "SECONDS_BETWEEN" not in sql_upper:
                logger.warning("Consulta SQL con filtro temporal pero sin SECONDS_BETWEEN")
                return False
        
        # Verificar que usa tablas AMC válidas
        valid_tables = [
            "CONVERSIONS", "CONVERSIONS_WITH_RELEVANCE", 
            "AMAZON_ATTRIBUTED_EVENTS_BY_CONVERSION_TIME", "AMAZON_ATTRIBUTED_EVENTS_BY_TRAFFIC_TIME",
            "DSP_IMPRESSIONS", "DSP_IMPRESSIONS_BY_MATCHED_SEGMENTS", "DSP_IMPRESSIONS_BY_USER_SEGMENTS",
            "DSP_CLICKS", "DSP_VIDEO_EVENTS_FEED", "DSP_VIEWS", "SPONSORED_ADS_TRAFFIC"
        ]
        
        has_valid_table = any(table in sql_upper for table in valid_tables)
        if not has_valid_table:
            logger.warning("Consulta SQL sin tablas AMC válidas")
            return False
            
        return True

    def _has_invalid_column_usage(self, sql_query: str) -> bool:
        """Verifica que no se mezclen columnas de diferentes tablas incorrectamente."""
        sql_lower = sql_query.lower()
        
        # Verificar si se usa 'impressions' en una tabla que no sea dsp_impressions
        if 'impressions' in sql_lower and 'dsp_impressions' not in sql_lower:
            return True
            
        # Verificar si se usa 'clicks' en una tabla que no sea dsp_clicks
        if 'clicks' in sql_lower and 'dsp_clicks' not in sql_lower:
            return True
            
        # Verificar si se usan columnas de conversiones en tablas incorrectas
        if ('conversions' in sql_lower or 'total_product_sales' in sql_lower) and \
        not any(table in sql_lower for table in ['conversions', 'conversions_with_relevance']):
            return True
            
        return False

    def _get_completion(self, prompt: str) -> str:
        """Obtiene una respuesta del modelo para el prompt dado."""
        try:
            # Preparar el sistema de mensajes
            system_message = (
                "Eres un asistente experto en Amazon Marketing Cloud (AMC). "
                "Tu tarea es proporcionar respuestas útiles y detalladas a consultas sobre análisis de datos, "
                "informes, métricas y optimización de campañas publicitarias en Amazon. "
                "Si te presentan un archivo, analiza su contenido cuidadosamente y responde basándote en él."
            )
            
            # Preparar la conversación con el contexto adecuado
            messages = [("system", system_message)]
            
            # Añadir contexto previo si existe
            if hasattr(self, 'conversation_context') and self.conversation_context:
                # Limitar a los últimos 5 mensajes para mantener el contexto reciente
                for message in self.conversation_context[-10:]:
                    role = "human" if message["role"] == "user" else "assistant"
                    messages.append((role, message["content"]))
            
            # Añadir el prompt actual
            messages.append(("human", prompt))
            
            # Llamar al modelo LLM
            logger.info(f"Enviando prompt al modelo, longitud total: {sum(len(m[1]) for m in messages)} caracteres")
            response = self.llm.invoke(messages)
            
            # Extraer y limpiar la respuesta
            answer = response.content if hasattr(response, "content") else str(response)
            answer = self._clean_response(answer)
            
            # Actualizar el contexto de la conversación
            self.conversation_context.append({"role": "user", "content": prompt})
            self.conversation_context.append({"role": "assistant", "content": answer})
            
            # Limitar el tamaño del contexto para evitar tokens excesivos
            if len(self.conversation_context) > 20:
                self.conversation_context = self.conversation_context[-20:]
                
            return answer
        except Exception as e:
            logger.error(f"Error en _get_completion: {str(e)}")
            return f"Lo siento, ocurrió un error al procesar tu consulta: {str(e)}"
    
    def analyze_with_context(self, query, file_content="", context_type="auto"):
        """Analiza una consulta con contexto opcional."""
        try:
            # Log para diagnóstico
            logger.info(f"analyze_with_context llamado con query de {len(query)} caracteres y file_content de {len(file_content)} caracteres")
            
            # Si hay contenido de archivo, crear un prompt enriquecido
            enriched_query = query
            if file_content and len(file_content) > 0:
                # Limitar el contenido del archivo si es muy grande
                if len(file_content) > 15000:  # Limitar a 15k caracteres
                    file_content = file_content[:15000] + "...\n[Contenido truncado debido a su tamaño]"
                
                enriched_query = f"Basándote en el siguiente contenido de archivo, responde a esta pregunta: '{query}'\n\nContenido del archivo:\n{file_content}"
                logger.info(f"Consulta enriquecida con contenido de archivo, longitud final: {len(enriched_query)} caracteres")
            
            # Preparar y enviar al modelo
            response = self._get_completion(enriched_query)
            
            # QUITAR LA PARTE DE GUARDAR EN EL HISTORIAL
            
            # Extraer conocimiento de la interacción
            try:
                self._extract_knowledge(query, response)
            except Exception as e:
                logger.error(f"Error extrayendo conocimiento: {str(e)}")
            
            return response
        except Exception as e:
            logger.error(f"Error en analyze_with_context: {str(e)}")
            return f"Lo siento, ocurrió un error al procesar tu consulta: {str(e)}"
        
    def _extract_knowledge(self, prompt: str, response: str):
        try:
            # Sólo extraer conocimiento de respuestas significativas (más de 50 caracteres)
            if len(response.strip()) < 50:
                logger.info("Respuesta demasiado corta para extraer conocimiento")
                return
                
            # Generar un tema basado en el prompt
            if len(prompt) > 50:
                topic = prompt[:50].strip() + "..."
            else:
                topic = prompt.strip()
                
            # Crear un hecho basado en la respuesta
            if len(response) > 200:
                fact = response[:200].strip() + "..."
            else:
                fact = response.strip()
                
            logger.info(f"Extrayendo conocimiento. Tema: {topic}")
            
            # Obtener la fecha actual como string en formato ISO
            current_time_iso = datetime.now().isoformat()
            
            # Actualizar el conocimiento
            existing = next((item for item in self.knowledge if item["topic"] == topic), None)
            
            if existing:
                # Si el tema ya existe, añadir este hecho si no está ya
                if fact not in existing["facts"]:
                    existing["facts"].append(fact)
                    # Limitar a 5 hechos por tema
                    existing["facts"] = existing["facts"][-5:]
                    existing["last_accessed"] = current_time_iso  # Guardar como string ISO
                    logger.info(f"Hecho añadido a tema existente: {topic}")
                else:
                    logger.info(f"Hecho ya existente para el tema: {topic}")
            else:
                # Si es un tema nuevo, crear nueva entrada
                self.knowledge.append({
                    "topic": topic, 
                    "facts": [fact],
                    "source": "chat",
                    "last_accessed": current_time_iso  # Guardar como string ISO
                })
                logger.info(f"Nuevo tema creado: {topic}")
                
            # Limitar el conocimiento total
            if len(self.knowledge) > 50:
                self.knowledge = self.knowledge[-50:]
                
            # Guardar el conocimiento actualizado
            saved = self.save_knowledge()
            logger.info(f"Conocimiento guardado: {'éxito' if saved else 'fallido'}")
            
        except Exception as e:
            logger.error(f"Error extrayendo conocimiento: {str(e)}")

    def detect_subscription_tables(self, sql_query: str) -> bool:
        subscription_tables = [
            "amazon_retail_purchases", "conversions_all", "segment_metadata", "audience_segments"
        ]
        return any(re.search(rf"\b{table}\b", sql_query, re.IGNORECASE) for table in subscription_tables)

    def generate_product_filters(self, natural_query: str) -> dict:
        system_prompt = (
            "Eres un experto en análisis de productos de Amazon. Analiza las consultas en lenguaje natural "
            "e identifica qué campos son necesarios para aplicar los filtros solicitados."
        )
        
        try:
            query_lower = natural_query.lower()
            needed_fields = []
            filters = {}
            error_message = None

            field_mappings = {
                'Price': ['precio', 'caro', 'barato', 'cuesta', 'value', 'cost', '$', 'dinero', 'económico'],
                'Reviews': ['reseña', 'review', 'opinión', 'comentario', 'valoración', 'evaluación'],
                'Rating': ['calificación', 'rating', 'estrellas', 'stars', 'puntuación'],
                'Stock': ['stock', 'inventario', 'disponible', 'existencia'],
                'Weight': ['peso', 'kilogramo', 'gramo', 'kg', 'g'],
                'Category': ['categoría', 'categoria', 'tipo', 'clasificación'],
                'Brand': ['marca', 'fabricante', 'productor'],
                'Size': ['tamaño', 'dimensión', 'medida', 'largo', 'ancho', 'alto'],
                'Color': ['color', 'tono', 'coloración'],
                'Prime': ['prime', 'amazon prime']
            }

            for field, keywords in field_mappings.items():
                if any(keyword in query_lower for keyword in keywords):
                    needed_fields.append(field)
                    
                    if field == 'Reviews':
                        filters['by_reviews'] = True
                        if any(word in query_lower for word in ['menos', 'inferior', 'bajo', 'menor']):
                            filters['less_reviews_than_us'] = True
                            filters['compare_all'] = True 
                    elif field == 'Price':
                        filters['by_price'] = True
                        if any(word in query_lower for word in ['mayor', 'más caro', 'superior']):
                            filters['higher_price_than_us'] = True
                    elif field == 'Rating':
                        filters['by_rating'] = True
                        if any(word in query_lower for word in ['menos', 'menor', 'bajo']):
                            filters['less_rating_than_us'] = True

            unavailable_fields = [field for field in needed_fields if field not in ['Price', 'Reviews', 'Rating']]
            if unavailable_fields:
                error_message = f"Los siguientes campos no están disponibles en el CSV: {', '.join(unavailable_fields)}. "
                error_message += "Se mostrarán todos los productos sin filtrar."
                filters = {}

            return {
                'filters': filters,
                'needed_fields': needed_fields,
                'error_message': error_message,
                'original_query': natural_query
            }

        except Exception as e:
            logger.error(f"Error generando filtros: {str(e)}")
            return { 
                'filters': {},
                'error_message': f"Error al procesar la consulta: {str(e)}",
                'needed_fields': [],
                'original_query': natural_query
            }