-- 1. Add user_id column to existing tables if they don't have it
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS user_id UUID DEFAULT auth.uid();

ALTER TABLE documents_chunks 
ADD COLUMN IF NOT EXISTS user_id UUID DEFAULT auth.uid();

-- (Assuming chat_sessions already has user_id from previous migration, but ensuring)
ALTER TABLE chat_sessions 
ADD COLUMN IF NOT EXISTS user_id UUID DEFAULT auth.uid();

ALTER TABLE chat_messages
ADD COLUMN IF NOT EXISTS user_id UUID DEFAULT auth.uid();

-- 2. Enable Row Level Security (RLS)
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

-- 3. Create Policies

-- Documents: Users can only see/insert/delete their own documents
DROP POLICY IF EXISTS "Users can manage their own documents" ON documents;
CREATE POLICY "Users can manage their own documents"
ON documents
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- Document Chunks: Users can only see/insert/delete their own chunks
DROP POLICY IF EXISTS "Users can manage their own chunks" ON documents_chunks;
CREATE POLICY "Users can manage their own chunks"
ON documents_chunks
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- Chat Sessions: Users can only see/insert/delete their own sessions
DROP POLICY IF EXISTS "Users can manage their own sessions" ON chat_sessions;
CREATE POLICY "Users can manage their own sessions"
ON chat_sessions
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- Chat Messages: Users can only see/insert/delete their own messages
-- Note: Messages should technically belong to a session which belongs to a user, 
-- but direct user_id link is safer and easier for RLS.
DROP POLICY IF EXISTS "Users can manage their own messages" ON chat_messages;
CREATE POLICY "Users can manage their own messages"
ON chat_messages
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);


-- 4. Update the Matching Function (RPC) to filter by user_id
-- We need to drop the old one and recreate it to add the filter
DROP FUNCTION IF EXISTS match_documents_gemini;

CREATE OR REPLACE FUNCTION match_documents_gemini (
  query_embedding vector(768),
  match_threshold float,
  match_count int,
  filter_user_id uuid DEFAULT auth.uid() 
)
RETURNS TABLE (
  id uuid,
  content text,
  document_id uuid,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    documents_chunks.id,
    documents_chunks.content,
    documents_chunks.document_id,
    1 - (documents_chunks.embedding_gemini <=> query_embedding) AS similarity
  FROM documents_chunks
  WHERE 1 - (documents_chunks.embedding_gemini <=> query_embedding) > match_threshold
  AND documents_chunks.user_id = filter_user_id -- Strict filtering by user_id
  ORDER BY documents_chunks.embedding_gemini <=> query_embedding
  LIMIT match_count;
END;
$$;
