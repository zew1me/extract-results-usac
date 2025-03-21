from dependency_injector import containers, providers
from src.scraper import CachedDataScraper, WebScraper

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    scraper = providers.Factory(
        lambda x: CachedDataScraper(
            x["athlete_basename"],
            x["event_series_basename_prefix"],
            x["to_id"]
        ) if x else WebScraper(),
        config
    )
