export interface StockProfile {
  business: string;
  sector: string;
  products: string;
  competitors: string[];
}

export type CellValue = string | number | null;

export type ResultRow = Record<string, unknown> & {
  stock_code: string;
  name: string;
  profile?: StockProfile | null;
};

export interface ResultsPayload {
  as_of_date: string | null;
  financial_year: number | null;
  generated_at: string | null;
  quote_text: string | null;
  quote_author: string | null;
  universe_total: number;
  universe_passed: number;
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: ResultRow[];
}

export type FilteredRow = Record<string, CellValue>;

export interface FilteredPayload {
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: FilteredRow[];
}

export interface PriceSuccessResponse {
  as_of: string;
  prices: Record<string, { close: number; fluc_rt: number }>;
}

export interface ApiErrorResponse { error: string }

export type PriceResponse = PriceSuccessResponse | ApiErrorResponse;

export interface KrxPriceRow {
  ISU_CD: string | number;
  TDD_CLSPRC: string | number;
  FLUC_RT: string | number;
}
