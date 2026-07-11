export interface PromptOptions {
    system?: string;
    user: string;
}
export interface SummarizeOptions {
    text: string;
    type?: 'key-points' | 'tl;dr' | 'teaser' | 'headline';
    format?: 'plain-text' | 'markdown';
    length?: 'short' | 'medium' | 'long';
}
export interface TranslateOptions {
    text: string;
    sourceLanguage?: string;
    targetLanguage?: string;
}
export interface WriteOptions {
    prompt: string;
    tone?: 'neutral' | 'formal' | 'informal';
    format?: 'plain-text' | 'markdown';
    length?: 'short' | 'medium' | 'long';
}
export declare function prompt(opts: PromptOptions): Promise<string>;
export declare function summarize(_opts: SummarizeOptions): Promise<string>;
export declare function translate(_opts: TranslateOptions): Promise<string>;
export declare function write(_opts: WriteOptions): Promise<string>;
