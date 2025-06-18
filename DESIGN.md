# DESIGN.md

This document outlines the driving use cases and design philosophy for the YNAB MCP Server, focused on helping heads of household manage family finances more effectively.

## Division of Responsibilities

**MCP Server provides**:
- Structured access to YNAB data with consistent formatting
- Efficient filtering and search capabilities
- Pagination for large datasets
- Clean abstractions over YNAB's API complexity

**LLM provides**:
- Natural language understanding
- Pattern recognition and analysis
- Intelligent summarization
- Actionable recommendations
- Context-aware interpretation

## Use Case Format Guide

Each use case follows this structure for clarity:
- **User says**: Natural language examples
- **Why it matters**: User context and pain points
- **MCP Server Role**: Which tools to use and what data they provide
- **LLM Role**: Analysis and intelligence needed
- **Example Implementation Flow**: Step-by-step approach (when helpful)
- **Edge Cases**: YNAB-specific gotchas to handle (when applicable)

## Core Use Cases

### 1. Weekly Family Finance Check-ins
**User says**: "How are we doing on our budget this month? Which categories are we overspending?"

**Why it matters**: Busy parents need quick weekly snapshots without opening YNAB. They want conversational summaries that highlight what needs attention.

**MCP Server Role**:
- `get_budget_month()` - Provides current month's budgeted amounts, activity, and balances
- `list_categories()` - Gets category structure for organization
- Returns clean, structured data with proper currency formatting

**LLM Role**:
- Interprets which categories are overspent/underspent
- Prioritizes what needs attention
- Suggests fund reallocation
- Generates conversational summary

**Example Implementation Flow**:
1. Call `get_budget_month()` to get current state
2. Identify categories where `balance < 0` (overspent)
3. Find categories with available funds (`balance > 0`)
4. Prioritize by spending velocity and days left in month
5. Format as conversational response with specific suggestions

**Edge Cases**:
- Handle credit card payment categories differently
- Consider "Inflow: Ready to Assign" as special
- Account for scheduled transactions not yet posted

### 2. Kid-Related Expense Tracking
**User says**: "How much have we spent on soccer this year?" or "Show me all transactions for Emma's activities"

**Why it matters**: Parents track expenses by child or activity for budgeting, tax deductions, or custody arrangements. Finding these across multiple categories and payees is tedious in YNAB.

**MCP Server Role**: 
- `find_payee()` - Searches for "soccer", "dance academy", etc.
- `list_transactions()` - Filters by payee_id, date ranges
- Handles pagination for large transaction sets
- Returns transaction details with amounts and dates

**LLM Role**:
- Identifies relevant search terms from natural language
- Aggregates totals across multiple payees/categories
- Groups related expenses
- Formats results for specific use (taxes, custody docs)

**Key Implementation Notes**:
- May need multiple payee searches (e.g., "Soccer Club", "Soccer Store", "Soccer Camp")
- Consider memo fields for additional context
- Date ranges should align with tax year or custody period

### 3. Subscription and Recurring Expense Audits
**User says**: "What subscriptions are we paying for?" or "List all our monthly recurring expenses"

**Why it matters**: Subscription creep affects every family. Parents need to identify forgotten subscriptions and understand their true monthly commitments.

**MCP Server Role**:
- `list_transactions()` - Provides transaction history with dates
- `list_payees()` - Gets payee details for merchant identification
- Efficient pagination for analyzing patterns over time

**LLM Role**:
- Pattern recognition to identify recurring transactions
- Frequency analysis (monthly, annual, etc.)
- Grouping by merchant
- Flagging unusual patterns or new subscriptions

### 4. Pre-Shopping Budget Checks
**User says**: "Can we afford to spend $300 at Costco today?" or "How much grocery money do we have left?"

**Why it matters**: Quick budget checks before shopping trips prevent overspending and the stress of moving money after the fact.

**MCP Server Role**:
- `get_budget_month()` - Current balances for relevant categories
- `list_categories()` - Category relationships and groupings
- Real-time accurate balance data

**LLM Role**:
- Maps "Costco shopping" to relevant categories (groceries, household, etc.)
- Calculates total available across multiple categories
- Suggests reallocation strategies
- Provides go/no-go recommendation

### 5. Financial Partnership Transparency
**User says**: "Give me a simple summary of our finances" or "Are we okay financially?" or "Did that Amazon return get credited?"

**Why it matters**: In many couples, one person manages the detailed budget while their partner needs simple, reassuring visibility without YNAB complexity. Partners want to understand the big picture and verify specific transactions without learning budgeting software.

**MCP Server Role**:
- `get_budget_month()` - Overall budget health data
- `list_accounts()` - Account balances for net worth
- `list_transactions()` - Recent transaction verification
- `find_payee()` - Quick lookup for specific merchants

**LLM Role**:
- Translates budget complexity into simple terms
- Provides reassuring summaries ("Yes, you're on track")
- Answers specific concerns without overwhelming detail
- Bridges the knowledge gap between budget manager and partner

### 6. End-of-Month Category Sweep
**User says**: "Which categories have money left over?" or "Help me zero out my budget"

**Why it matters**: YNAB's zero-based budgeting requires monthly cleanup. Parents need quick identification of surplus funds and smart reallocation suggestions.

**MCP Server Role**:
- `get_budget_month()` - All category balances for current month
- `list_category_groups()` - Organized view of budget structure
- Accurate to-the-penny balance data

**LLM Role**:
- Identifies categories with positive balances
- Analyzes historical spending to suggest reallocations
- Prioritizes based on upcoming needs
- Future: Generates reallocation transactions

### 7. Emergency Fund Reality Checks
**User says**: "How many months could we survive on our emergency fund?" or "What's our true available emergency money?"

**Why it matters**: Provides peace of mind by calculating realistic burn rates based on essential expenses and actual family spending patterns.

**MCP Server Role**:
- `list_accounts()` - Gets emergency fund account balances
- `list_transactions()` - Historical spending data for analysis
- `list_categories()` - Category structure for expense classification

**LLM Role**:
- Categorizes expenses as essential vs. discretionary
- Calculates average monthly burn rate
- Projects survival duration
- Scenario modeling based on different assumptions

### 8. Financial Scenario Planning
**User says**: "What if I get a 10% raise?" or "Can we afford a $400/month car payment?" or "What happens if we have another baby?"

**Why it matters**: Families need to model major financial decisions before committing. They want to understand how changes in income, expenses, or family size would impact their budget without actually making changes in YNAB.

**MCP Server Role**:
- `get_budget_month()` - Current budget as baseline
- `list_transactions()` - Historical spending patterns
- `list_categories()` - Understanding fixed vs. variable expenses
- `list_accounts()` - Current financial position

**LLM Role**:
- Models income changes across categories
- Projects new expense impacts
- Identifies categories that would need adjustment
- Calculates how long until savings goals are met
- Suggests budget reallocations for new scenarios

**Future MCP Tools Needed**:
- `create_budget_scenario()` - Clone budget for what-if analysis
- `get_category_spending_history()` - Trends over time for better projections

## Design Principles for Use Cases

1. **Conversational First**: Every query should feel natural to speak or type
2. **Context Aware**: Understand "we", "our", "the kids" in the context of a family
3. **Action Oriented**: Don't just report data, suggest next steps
4. **Time Sensitive**: Respect that parents are asking between activities
5. **Trust Building**: Be transparent about calculations and assumptions

## Future Use Case Directions

### Receipt/Transaction Quick Entry
**User says**: "Add Costco $127.43 groceries and household"

**Future MCP Tools Needed**:
- `create_transaction()` - Add new transactions with splits
- `get_recent_payees()` - Smart payee matching
- `suggest_categories()` - Based on payee history

### Bill Reminders
**User says**: "What bills are due this week?"

**MCP Server Role**:
- `list_scheduled_transactions()` - Future tool for recurring transactions
- Current workaround: Analyze transaction history for patterns

### Import Assistance
**User says**: "Help me categorize these Venmo transactions"

**Future MCP Tools Needed**:
- `import_transactions()` - Bulk import capability
- `update_transaction()` - Modify imported transactions
- `match_payees()` - Fuzzy matching for payee cleanup

## Tool Implementation Status

### Currently Implemented (10 tools)
- ✅ `list_budgets()` - All use cases
- ✅ `list_accounts()` - Emergency fund calculations
- ✅ `list_categories()` - Budget structure understanding
- ✅ `list_category_groups()` - Efficient category overview
- ✅ `get_budget_month()` - Weekly check-ins, category sweep
- ✅ `get_month_category_by_id()` - Specific category details
- ✅ `list_transactions()` - Expense tracking, subscriptions, transparency
- ✅ `list_payees()` - Payee analysis
- ✅ `find_payee()` - Efficient payee search

### Planned Tools (SDK-supported)
- 🔄 `list_scheduled_transactions()` - Bill reminders, recurring expenses
- 🔄 `create_transaction()` - Quick entry
- 🔄 `update_transaction()` - Import assistance
- 🔄 `import_transactions()` - Bulk import

### Optimization Considerations
The SDK offers specialized transaction endpoints that could optimize specific use cases:
- `get_transactions_by_account()` - Direct account filtering
- `get_transactions_by_category()` - Direct category filtering
- `get_transactions_by_month()` - Month-specific queries
- `get_transactions_by_payee()` - Direct payee filtering

**Current approach**: Single `list_transactions()` with flexible filtering
**Trade-offs**: 
- ✅ Simpler API surface for LLMs to learn
- ✅ One tool handles all filtering combinations
- ❌ Potentially less efficient for single-filter queries
- ❌ May miss SDK-specific optimizations

**Recommendation**: Keep the single `list_transactions()` approach because:
1. LLMs perform better with fewer, more flexible tools
2. Most use cases need multiple filters anyway (date + payee, category + amount)
3. The performance difference is negligible for household-scale data
4. Reduces tool discovery complexity for the LLM

### Creative Solutions Needed
- 💡 Smart payee matching - Build on existing tools
- 💡 Category suggestions - Analyze transaction history
- 💡 Fuzzy payee matching - Custom logic required

## Success Metrics

A use case is successful when:
- It saves the user time vs. using YNAB directly
- It provides insights not easily visible in YNAB's interface
- It helps prevent financial stress or surprises
- It works within the natural flow of family life