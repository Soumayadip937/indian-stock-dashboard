def apply_advanced_filters(stocks, filters):
    """Apply advanced filtering based on user criteria"""
    filtered = []
    
    for stock in stocks:
        if filters.get('min_market_cap') and stock['market_cap'] < filters['min_market_cap']:
            continue
        
        if filters.get('max_pe') and stock['pe_ratio'] > filters['max_pe']:
            continue
        
        if filters.get('min_volume') and stock['volume'] < filters['min_volume']:
            continue
        
        if filters.get('sectors') and stock['sector'] not in filters['sectors']:
            continue
        
        filtered.append(stock)
    
    return filtered
